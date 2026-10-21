"""
Envío de mensajes de plantilla (template) vía la WhatsApp Cloud API de Meta.
"""

import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)

API_VERSION = os.environ.get("META_API_VERSION", "v23.0")

# Códigos HTTP que vale la pena reintentar: 429 es el límite de tasa de
# Meta y los 5xx son problemas de su lado. El resto de los 4xx son
# errores de nuestro pedido (plantilla mal armada, número inexistente) y
# reintentarlos da siempre lo mismo.
HTTP_REINTENTABLES = (429, 500, 502, 503, 504)

# Cuántas veces se reintenta un mismo mensaje antes de darlo por perdido,
# y la espera base del backoff exponencial (2s, 4s, 8s...).
REINTENTOS = 3
ESPERA_BASE = 2

# Tope de espera, para que un Retry-After alto de Meta no deje el envío
# colgado media hora.
ESPERA_MAXIMA = 60

# Una sola sesión para todo el envío: sin esto, mandar a 431 socios abre
# 431 conexiones TLS nuevas. Con keep-alive se reusa la misma.
_sesion = None


def obtener_sesion():
    """Devuelve la sesión HTTP compartida, creándola la primera vez."""
    global _sesion
    if _sesion is None:
        _sesion = requests.Session()
    return _sesion


def _espera_sugerida(respuesta, intento):
    """
    Cuánto esperar antes del próximo intento.

    Usa el header Retry-After si Meta lo mandó (es la espera que el
    propio Meta pide); si no, backoff exponencial.
    """
    retry_after = respuesta.headers.get("Retry-After") if respuesta is not None else None

    if retry_after:
        try:
            return min(float(retry_after), ESPERA_MAXIMA)
        except ValueError:
            pass

    return min(ESPERA_BASE * (2 ** intento), ESPERA_MAXIMA)

# Idioma por defecto de la plantilla, usado si enviar_plantilla no recibe
# uno explícito. Debe coincidir con el idioma configurado para la
# plantilla aprobada en Meta Business Manager.
IDIOMA_PLANTILLA = "es_AR"

# Meta rechaza los parámetros que contienen saltos de línea, tabulaciones
# o más de cuatro espacios seguidos (error 132000). El texto multilínea
# tiene que estar en el cuerpo de la plantilla, no en una variable.
ESPACIOS_A_COLAPSAR = re.compile(r"\s+")


def limpiar_parametro(valor):
    """
    Deja un valor de variable en un formato que Meta acepte.

    Colapsa cualquier secuencia de espacios en blanco (incluidos saltos
    de línea y tabs) en un solo espacio y recorta los extremos.

    Args:
        valor: valor crudo, típicamente una celda del CSV.

    Returns:
        str: el valor en una sola línea. Puede quedar vacío, y un
        parámetro vacío también es rechazado por Meta: quien llame debe
        controlarlo antes de enviar.
    """
    if valor is None:
        return ""
    return ESPACIOS_A_COLAPSAR.sub(" ", str(valor)).strip()


def _construir_componentes(parametros):
    """
    Arma el componente "body" del payload según el tipo de `parametros`.

    Un dict produce parámetros nombrados (plantillas NAMED, con
    "parameter_name"); una lista o tupla produce parámetros posicionales
    (plantillas POSITIONAL), en el orden recibido.

    Devuelve None si no hay parámetros: las plantillas sin variables
    rechazan un "components" vacío.
    """
    if not parametros:
        return None

    if isinstance(parametros, dict):
        lista = [
            {"type": "text", "parameter_name": nombre, "text": str(valor)}
            for nombre, valor in parametros.items()
        ]
    else:
        lista = [{"type": "text", "text": str(valor)} for valor in parametros]

    return [{"type": "body", "parameters": lista}]


def enviar_plantilla(
    numero_destino,
    nombre_plantilla,
    parametros,
    access_token,
    phone_number_id,
    idioma=IDIOMA_PLANTILLA,
):
    """
    Envía un mensaje de plantilla a un número vía la WhatsApp Cloud API.

    Args:
        numero_destino: número en formato E.164 (ej: "+5493874516830").
        nombre_plantilla: nombre de la plantilla aprobada en Meta.
        parametros: valores de las variables del componente "body".
            - dict {nombre_variable: valor} para plantillas con
              parameter_format NAMED (el orden no importa, cada valor
              viaja con su "parameter_name").
            - lista de valores, en orden, para plantillas POSITIONAL
              ({{1}}, {{2}}...).
            Si está vacío, el payload no incluye "components"
            (plantillas sin variables, como "hello_world" o
            "bienvenida_menu_principal", rechazan un components vacío).
        access_token: token de acceso de la app/WABA de Meta.
        phone_number_id: ID del número de teléfono emisor de WhatsApp Business.
        idioma: código de idioma de la plantilla (ej: "es_AR", "en_US").
            Por defecto "es_AR".

    Returns:
        tuple[bool, str]: (exito, detalle).
        Si exito es True, detalle es el message_id devuelto por Meta.
        Si exito es False, detalle incluye el código HTTP y, si vienen en
        la respuesta, "message", "code", "error_subcode" y
        "error_data.details" del error de Meta.
    """
    url = f"https://graph.facebook.com/{API_VERSION}/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    template = {
        "name": nombre_plantilla,
        "language": {"code": idioma},
    }

    componentes = _construir_componentes(parametros)
    if componentes:
        template["components"] = componentes

    payload = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "template",
        "template": template,
    }

    sesion = obtener_sesion()
    respuesta = None

    # Un 429 o un 5xx no significan que el mensaje no se pueda mandar,
    # solo que ahora no: se reintenta con backoff antes de darlo por
    # fallido y dejar al socio sin el mensaje.
    for intento in range(REINTENTOS + 1):
        try:
            respuesta = sesion.post(url, headers=headers, json=payload, timeout=15)
        except requests.RequestException as e:
            if intento == REINTENTOS:
                return False, f"Error de conexión: {e}"
            espera = _espera_sugerida(None, intento)
            logger.warning(
                "Error de conexión con Meta (%s). Reintento %d/%d en %.0fs.",
                e, intento + 1, REINTENTOS, espera,
            )
            time.sleep(espera)
            continue

        if respuesta.status_code not in HTTP_REINTENTABLES:
            break

        if intento == REINTENTOS:
            break

        espera = _espera_sugerida(respuesta, intento)
        logger.warning(
            "Meta respondió HTTP %d. Reintento %d/%d en %.0fs.",
            respuesta.status_code, intento + 1, REINTENTOS, espera,
        )
        time.sleep(espera)

    try:
        data = respuesta.json()
    except ValueError:
        data = {}

    if respuesta.ok:
        try:
            message_id = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            message_id = ""
        return True, message_id

    error = {}
    if isinstance(data, dict):
        error = data.get("error") or {}

    error_msg = error.get("message") or respuesta.text

    detalle_partes = [f"HTTP {respuesta.status_code}", str(error_msg)]

    if "code" in error:
        detalle_partes.append(f"code={error['code']}")
    if "error_subcode" in error:
        detalle_partes.append(f"error_subcode={error['error_subcode']}")

    error_data = error.get("error_data")
    if isinstance(error_data, dict) and "details" in error_data:
        detalle_partes.append(f"error_data.details={error_data['details']}")

    return False, " | ".join(detalle_partes)


def consultar_plantilla(id_plantilla, access_token):
    """
    Consulta en Meta el estado actual de una plantilla por su id.

    Sirve para no arrancar un envío masivo con una plantilla que quedó
    en PENDING, REJECTED, PAUSED o DISABLED: Meta rechazaría cada
    mensaje por separado.

    Args:
        id_plantilla: id numérico de la plantilla en Meta.
        access_token: token de acceso de la app/WABA de Meta.

    Returns:
        tuple[dict | None, str]: (datos, detalle).
        Si la consulta funcionó, datos trae al menos "name", "language",
        "status" y "parameter_format", y detalle queda vacío.
        Si falló, datos es None y detalle explica por qué (la consulta
        es informativa: quien llama decide si sigue igual).
    """
    url = f"https://graph.facebook.com/{API_VERSION}/{id_plantilla}"
    parametros = {"fields": "name,language,status,category,parameter_format"}
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        respuesta = obtener_sesion().get(url, headers=headers, params=parametros, timeout=15)
    except requests.RequestException as e:
        return None, f"Error de conexión: {e}"

    try:
        data = respuesta.json()
    except ValueError:
        return None, f"HTTP {respuesta.status_code}: respuesta no es JSON"

    if not respuesta.ok:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        return None, f"HTTP {respuesta.status_code}: {error.get('message', respuesta.text)}"

    return data, ""


def enviar_mensaje_texto(
    numero_destino: str,
    texto: str,
    access_token: str,
    phone_number_id: str,
    mensaje_contexto_id: str | None = None,
) -> tuple[bool, str]:
    """
    Envía un mensaje de texto plano vía la WhatsApp Cloud API.
    Apto para respuestas a socios dentro de la ventana de atención de 24 horas.

    Args:
        numero_destino: número en formato internacional o local (ej: "+5493874516830").
        texto: contenido del mensaje a enviar.
        access_token: token de acceso de Meta.
        phone_number_id: ID del número de teléfono emisor de WhatsApp Business.
        mensaje_contexto_id: ID del mensaje original al que se responde (opcional).

    Returns:
        tuple[bool, str]: (exito, detalle_o_id).
        Si exito es True, detalle es el message_id devuelto por Meta.
        Si exito es False, detalle es la descripción clara del error.
    """
    url = f"https://graph.facebook.com/{API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    destino_str = str(numero_destino).strip()
    if not destino_str.startswith("+"):
        destino_str = f"+{destino_str}"

    payload = {
        "messaging_product": "whatsapp",
        "to": destino_str,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": texto,
        },
    }

    if mensaje_contexto_id:
        payload["context"] = {"message_id": mensaje_contexto_id}

    sesion = obtener_sesion()
    respuesta = None

    for intento in range(REINTENTOS + 1):
        try:
            respuesta = sesion.post(url, headers=headers, json=payload, timeout=15)
        except requests.RequestException as e:
            if intento == REINTENTOS:
                return False, f"Error de conexión con Meta: {e}"
            espera = _espera_sugerida(None, intento)
            logger.warning("Error de conexión enviando texto (%s). Reintento %d/%d en %.0fs.", e, intento + 1, REINTENTOS, espera)
            time.sleep(espera)
            continue

        if respuesta.status_code not in HTTP_REINTENTABLES:
            break

        if intento == REINTENTOS:
            break

        espera = _espera_sugerida(respuesta, intento)
        logger.warning("Meta respondió HTTP %d en envío de texto. Reintento %d/%d en %.0fs.", respuesta.status_code, intento + 1, REINTENTOS, espera)
        time.sleep(espera)

    try:
        data = respuesta.json()
    except (ValueError, AttributeError):
        data = {}

    if respuesta and respuesta.ok:
        try:
            message_id = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            message_id = ""
        return True, message_id

    error = {}
    if isinstance(data, dict):
        error = data.get("error") or {}

    error_code = error.get("code")
    error_msg = error.get("message") or (respuesta.text if respuesta else "Sin respuesta")

    if error_code == 131047:
        return False, "Ventana de 24 horas vencida: El socio no ha enviado mensajes en las últimas 24 horas. Meta exige utilizar una plantilla aprobada para contactarlo."

    status_code = respuesta.status_code if respuesta else 0
    detalle_partes = [f"HTTP {status_code}", str(error_msg)]

    if "code" in error:
        detalle_partes.append(f"code={error['code']}")
    if "error_subcode" in error:
        detalle_partes.append(f"error_subcode={error['error_subcode']}")
    error_data = error.get("error_data")
    if isinstance(error_data, dict) and "details" in error_data:
        detalle_partes.append(f"detalles={error_data['details']}")

    return False, " | ".join(detalle_partes)

