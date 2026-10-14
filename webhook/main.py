"""
Webhook de WhatsApp Business API (Meta) con FastAPI.

- GET /webhook  -> verificación inicial que exige Meta al configurar el webhook.
- POST /webhook -> recepción de eventos/mensajes entrantes.

El POST valida la firma, guarda siempre el payload crudo en Oracle
(wsp_raw_inbox) y además registra en wsp_log_mensajes:

- los "statuses" (confirmaciones de mensajes que nosotros enviamos),
  con direccion='SALIENTE';
- los "messages" (mensajes que nos escriben los contactos), con
  direccion='ENTRANTE'.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, Response

from webhook.db import guardar_log_mensaje, guardar_raw, marcar_procesado
from webhook.verify import verificar_firma

# Sin esto el root logger queda en WARNING y los logger.info de
# webhook.main y webhook.db no se imprimen en ninguna parte: en la salida
# del proceso solo se verían las líneas de acceso de uvicorn.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("webhook.main")

# Carga de variables de entorno desde rutas absolutas, tal como se pidió.
CONFIG_DIR = Path("/opt/userchuck/config")
load_dotenv(CONFIG_DIR / "database.env")
load_dotenv(CONFIG_DIR / "meta.env")

app = FastAPI(title="WhatsApp Business Webhook")

# Tipos de mensaje entrante que traen un adjunto alojado en los
# servidores de Meta: su id se guarda en wsp_log_mensajes.file_id y sirve
# para bajar el archivo después con GET /<media-id>.
TIPOS_CON_ADJUNTO = ("image", "document", "audio", "video", "sticker")


@app.get("/webhook")
async def verificar_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """
    Endpoint de verificación inicial que Meta llama al configurar el
    webhook en la app de WhatsApp Business.
    """
    verify_token_esperado = os.environ.get("META_VERIFY_TOKEN")

    if (
        hub_mode == "subscribe"
        and hub_verify_token is not None
        and verify_token_esperado is not None
        and hub_verify_token == verify_token_esperado
    ):
        return Response(content=hub_challenge or "", media_type="text/plain")

    return Response(status_code=403)


def _extraer_statuses(data: dict) -> list[dict]:
    """
    Recorre entry[].changes[].value.statuses[] y devuelve la lista plana
    de todos los objetos "status" encontrados en el payload.

    Devuelve lista vacía si el payload no trae statuses (por ejemplo,
    eventos "messages" entrantes) o si la estructura no es la esperada.
    """
    statuses: list[dict] = []
    for entry in data.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            statuses.extend(value.get("statuses", []) or [])
    return statuses


def _extraer_mensajes(data: dict) -> list[tuple[dict, dict]]:
    """
    Recorre entry[].changes[].value.messages[] y devuelve una lista de
    tuplas (mensaje, nombres), donde `nombres` mapea wa_id -> nombre de
    perfil según value.contacts[] del mismo change.

    El nombre viaja aparte porque Meta lo manda una sola vez por change,
    en "contacts", no dentro de cada mensaje.

    Devuelve lista vacía si el payload no trae mensajes entrantes (por
    ejemplo, eventos "statuses") o si la estructura no es la esperada.
    """
    mensajes: list[tuple[dict, dict]] = []

    for entry in data.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            entrantes = value.get("messages", []) or []
            if not entrantes:
                continue

            nombres: dict[str, str | None] = {}
            for contacto in value.get("contacts", []) or []:
                wa_id = contacto.get("wa_id")
                if wa_id:
                    perfil = contacto.get("profile", {}) or {}
                    nombres[wa_id] = perfil.get("name")

            for mensaje in entrantes:
                mensajes.append((mensaje, nombres))

    return mensajes


def _extraer_texto(mensaje: dict) -> str | None:
    """
    Devuelve el texto legible de un mensaje entrante según su tipo.

    Para los tipos que no tienen un texto obvio (contacts, order,
    system, unknown...) devuelve None: el contenido completo siempre
    queda igual en json_puro.
    """
    tipo = mensaje.get("type")

    if tipo == "text":
        return (mensaje.get("text", {}) or {}).get("body")

    if tipo in TIPOS_CON_ADJUNTO:
        # image/video/document pueden traer caption; document, filename.
        adjunto = mensaje.get(tipo, {}) or {}
        return adjunto.get("caption") or adjunto.get("filename")

    if tipo == "button":
        return (mensaje.get("button", {}) or {}).get("text")

    if tipo == "interactive":
        interactivo = mensaje.get("interactive", {}) or {}
        respuesta = interactivo.get("button_reply") or interactivo.get("list_reply") or {}
        return respuesta.get("title")

    if tipo == "reaction":
        return (mensaje.get("reaction", {}) or {}).get("emoji")

    if tipo == "location":
        ubicacion = mensaje.get("location", {}) or {}
        coordenadas = f"{ubicacion.get('latitude')},{ubicacion.get('longitude')}"
        nombre = ubicacion.get("name") or ubicacion.get("address")
        return f"{nombre} ({coordenadas})" if nombre else coordenadas

    return None


def _extraer_file_id(mensaje: dict) -> str | None:
    """
    Devuelve el id del adjunto en los servidores de Meta, para los
    mensajes que traen media. None para el resto.
    """
    tipo = mensaje.get("type")
    if tipo not in TIPOS_CON_ADJUNTO:
        return None
    return (mensaje.get(tipo, {}) or {}).get("id")


def _recortar(valor: str | None, largo_bytes: int) -> str | None:
    """
    Recorta `valor` al largo máximo de su columna en wsp_log_mensajes.

    El recorte es por bytes UTF-8 y no por caracteres porque las columnas
    están declaradas en BYTE (VARCHAR2(100) con semántica de byte): un
    nombre de perfil de WhatsApp con acentos o emojis ocupa más bytes que
    caracteres, y pasarse hace fallar el INSERT entero con ORA-12899.

    Si el corte cae en medio de un carácter multibyte, ese carácter se
    descarta: vale más perder una letra que perder el registro.
    """
    if valor is None:
        return None

    codificado = valor.encode("utf-8")
    if len(codificado) <= largo_bytes:
        return valor

    return codificado[:largo_bytes].decode("utf-8", errors="ignore")


def _procesar_evento(data: dict) -> None:
    """
    Procesa el payload ya parseado del webhook.

    Guarda en wsp_log_mensajes un registro por cada:

    - "status" (delivered/read/failed de mensajes que nosotros
      enviamos), con direccion='SALIENTE';
    - "message" entrante (lo que nos escribe un contacto), con
      direccion='ENTRANTE'.

    Cualquier otro tipo de evento queda solo en wsp_raw_inbox, sin más
    procesamiento.

    Puede lanzar excepciones (de parseo o de Oracle): quien la llama
    decide qué hacer con eso.

    Raises:
        RuntimeError: si algún INSERT en wsp_log_mensajes falló.
            guardar_log_mensaje atrapa los errores de Oracle y devuelve
            None en vez de propagarlos, así que sin este control el
            evento terminaría marcado PROCESADO en wsp_raw_inbox —y por
            lo tanto nunca reprocesado— habiendo perdido el mensaje.
    """
    guardados = []

    for status in _extraer_statuses(data):
        guardados.append(guardar_log_mensaje(
            wa_id=_recortar(status.get("recipient_id"), 50),
            wa_name=None,
            wsp_msg_id=_recortar(status.get("id"), 200),
            direccion="SALIENTE",
            tipo_mensaje="status",
            texto_mensaje=status.get("status"),
            json_puro=json.dumps(status, ensure_ascii=False),
        ))

    for mensaje, nombres in _extraer_mensajes(data):
        wa_id = mensaje.get("from")
        guardados.append(guardar_log_mensaje(
            wa_id=_recortar(wa_id, 50),
            wa_name=_recortar(nombres.get(wa_id), 100),
            wsp_msg_id=_recortar(mensaje.get("id"), 200),
            direccion="ENTRANTE",
            tipo_mensaje=_recortar(mensaje.get("type"), 20),
            texto_mensaje=_extraer_texto(mensaje),
            json_puro=json.dumps(mensaje, ensure_ascii=False),
            file_id=_recortar(_extraer_file_id(mensaje), 200),
        ))

    fallidos = sum(1 for id_log in guardados if id_log is None)
    if fallidos:
        raise RuntimeError(
            f"No se pudieron guardar {fallidos} de {len(guardados)} registros "
            "en wsp_log_mensajes"
        )


@app.post("/webhook")
async def recibir_evento(request: Request):
    """
    Recibe eventos de WhatsApp (mensajes, estados, etc.).

    Valida la firma HMAC del body raw antes de procesar nada. Después:

    1. Guarda siempre el payload crudo en wsp_raw_inbox (red de
       seguridad: esto no debe fallar nunca el flujo).
    2. Intenta parsear y procesar el evento (statuses -> wsp_log_mensajes).
    3. Marca el resultado (éxito/error) en wsp_raw_inbox.

    Responde 200 si el payload crudo quedó guardado, aunque el
    procesamiento posterior haya fallado: en ese caso el error queda
    registrado en estado_proceso y la fila se puede reprocesar, así que
    no hace falta que Meta reintente.

    Si no se pudo guardar ni el payload crudo, responde 500. wsp_raw_inbox
    es la red de seguridad de todo el diseño: cuando la red misma falla,
    el reintento de Meta (que tiene backoff propio y sigue por días) es lo
    único que evita perder el evento.
    """
    payload_bytes = await request.body()
    firma_header = request.headers.get("X-Hub-Signature-256")

    if not verificar_firma(payload_bytes, firma_header):
        return Response(status_code=403)

    payload_texto = payload_bytes.decode("utf-8", errors="replace")
    ip_origen = request.client.host if request.client else None
    headers_texto = json.dumps(dict(request.headers), ensure_ascii=False)

    id_raw = guardar_raw(
        payload_json=payload_texto,
        ip_origen=ip_origen,
        headers_json=headers_texto,
    )

    if id_raw is None:
        logger.error(
            "No se pudo guardar el payload en wsp_raw_inbox. Se responde 500 para "
            "que Meta reintente en lugar de dar el evento por entregado."
        )
        return Response(status_code=500)

    try:
        data = json.loads(payload_texto)
        _procesar_evento(data)
        marcar_procesado(id_raw, exito=True)
    except Exception as error:  # noqa: BLE001 - no queremos crashear el webhook
        logger.exception("Error procesando evento del webhook (id_raw=%s)", id_raw)
        marcar_procesado(id_raw, exito=False, mensaje_error=_recortar(str(error), 4000))

    return Response(status_code=200)
