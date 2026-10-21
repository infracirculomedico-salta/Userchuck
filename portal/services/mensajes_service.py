"""
Servicio de Gestión de Mensajería Individual, Conversaciones y Respuestas
para el Portal de WhatsApp del Círculo Médico de Salta.
"""

import csv
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from portal.config import (
    CONTACTOS_DIR,
    META_ACCESS_TOKEN,
    META_PHONE_NUMBER_ID,
    PROJECT_ROOT,
)
from portal.database import DBManager
from portal.services.plantillas_service import PlantillasService

sys.path.insert(0, str(PROJECT_ROOT / "sender"))
try:
    from normalizar import normalizar_numero_con_motivo
    from plantillas import PLANTILLAS as PLANTILLAS_CONFIG
    from whatsapp_api import enviar_mensaje_texto, enviar_plantilla, limpiar_parametro
except ImportError:
    PLANTILLAS_CONFIG = {}
    def normalizar_numero_con_motivo(n):
        return n, ""
    def enviar_mensaje_texto(*args, **kwargs):
        return False, "Módulo whatsapp_api no disponible"
    def enviar_plantilla(*args, **kwargs):
        return False, "Módulo whatsapp_api no disponible"
    def limpiar_parametro(v):
        return str(v or "")

logger = logging.getLogger("portal.mensajes")

# Cache de padrón de contactos en memoria (TTL: 60s)
_cache_padron = {}
_cache_padron_ts = 0


def _obtener_padron_socios() -> dict[str, dict]:
    """
    Lee los CSVs de la carpeta contactos y la tabla wsp_contactos,
    armando un mapa de número normalizado (sin signos) -> datos del socio.
    """
    global _cache_padron, _cache_padron_ts
    ahora = time.time()
    if _cache_padron and (ahora - _cache_padron_ts) < 60:
        return _cache_padron

    padron = {}

    # 1. Intentar desde tabla wsp_contactos si hay datos
    try:
        sql = "SELECT matricula, dni, nombre_completo, email, telefono_original, telefono_normalizado, estado_consentimiento FROM wsp_contactos"
        filas = DBManager.execute_query(sql, sql)
        for f in filas:
            norm = f.get("telefono_normalizado") or f.get("telefono_original") or ""
            digitos = re.sub(r"\D", "", str(norm))
            if digitos:
                padron[digitos] = {
                    "nombre": f.get("nombre_completo", ""),
                    "matricula": f.get("matricula", ""),
                    "dni": f.get("dni", ""),
                    "email": f.get("email", ""),
                    "consentimiento": f.get("estado_consentimiento", "ACEPTO"),
                    "fuente": "BD",
                }
    except Exception as e:
        logger.debug("No se pudo cargar desde wsp_contactos: %s", e)

    # 2. Complementar o cargar desde archivos CSV en contactos/
    try:
        if CONTACTOS_DIR.exists():
            for archivo_csv in CONTACTOS_DIR.glob("*.csv"):
                try:
                    with open(archivo_csv, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                        primera_linea = f.readline()
                        if not primera_linea:
                            continue
                        sep = ";" if ";" in primera_linea else ("," if "," in primera_linea else "\t")
                        f.seek(0)
                        lector = csv.DictReader(f, delimiter=sep)
                        for fila in lector:
                            tel = fila.get("WHATSAPP") or fila.get("TELEFONO") or ""
                            norm, _ = normalizar_numero_con_motivo(tel)
                            digitos = re.sub(r"\D", "", norm or tel)
                            if digitos and digitos not in padron:
                                padron[digitos] = {
                                    "nombre": fila.get("APEYNOM") or fila.get("NOMBRE") or "Socio CMS",
                                    "matricula": fila.get("MATRICULA") or "",
                                    "dni": fila.get("DNI") or "",
                                    "email": fila.get("MAIL") or fila.get("EMAIL") or "",
                                    "consentimiento": fila.get("ESTADO_CONSENTIMIENTO") or "ACEPTO",
                                    "fuente": archivo_csv.name,
                                }
                except Exception as ex_f:
                    logger.warning("Error leyendo CSV %s: %s", archivo_csv, ex_f)
    except Exception as ex:
        logger.warning("Error buscando CSVs de contactos: %s", ex)

    _cache_padron = padron
    _cache_padron_ts = ahora
    return padron


class MensajesService:

    @classmethod
    def obtener_conversaciones(
        cls,
        busqueda: Optional[str] = None,
        filtro: Optional[str] = None,
    ) -> list[dict]:
        """
        Retorna la lista de conversaciones agrupadas por número (wa_id),
        indicando últimos mensajes recibidos, estado de respuesta y datos del socio.
        """
        padron = _obtener_padron_socios()

        sql_base = """
            SELECT 
                l.wa_id,
                agg.total_mensajes,
                agg.total_entrantes,
                agg.ultimo_entrante_id,
                agg.ultimo_saliente_id,
                agg.ultima_fecha_entrante,
                agg.wa_name_entrante,
                l.id_log as ultimo_id,
                COALESCE(l.wa_name, agg.wa_name_entrante) as wa_name,
                l.direccion as ultima_direccion,
                l.tipo_mensaje as ultimo_tipo,
                l.texto_mensaje as ultimo_texto,
                l.estado_status as ultimo_estado,
                l.fecha_registro as ultima_fecha
            FROM (
                SELECT 
                    wa_id,
                    COUNT(*) as total_mensajes,
                    SUM(CASE WHEN direccion = 'ENTRANTE' THEN 1 ELSE 0 END) as total_entrantes,
                    MAX(CASE WHEN direccion = 'ENTRANTE' THEN id_log ELSE NULL END) as ultimo_entrante_id,
                    MAX(CASE WHEN direccion = 'SALIENTE' AND (tipo_mensaje IS NULL OR tipo_mensaje != 'status') THEN id_log ELSE NULL END) as ultimo_saliente_id,
                    MAX(CASE WHEN direccion = 'ENTRANTE' THEN fecha_registro ELSE NULL END) as ultima_fecha_entrante,
                    MAX(CASE WHEN direccion = 'ENTRANTE' AND wa_name IS NOT NULL AND LENGTH(TRIM(wa_name)) > 0 THEN wa_name ELSE NULL END) as wa_name_entrante,
                    COALESCE(MAX(CASE WHEN tipo_mensaje IS NULL OR tipo_mensaje != 'status' THEN id_log ELSE NULL END), MAX(id_log)) as max_id
                FROM wsp_log_mensajes
                WHERE wa_id IS NOT NULL AND LENGTH(TRIM(wa_id)) > 0
                GROUP BY wa_id
            ) agg
            JOIN wsp_log_mensajes l ON l.id_log = agg.max_id
            ORDER BY agg.max_id DESC
        """

        filas = DBManager.execute_query(sql_base, sql_base)
        conversaciones = []
        termino = busqueda.lower().strip() if (busqueda and isinstance(busqueda, str)) else None
        if termino == "":
            termino = None
        filtro_str = (filtro or "todos").lower().strip()

        for f in filas:
            wa_id = str(f.get("wa_id") or "").strip()
            if not wa_id:
                continue

            digitos = re.sub(r"\D", "", wa_id)
            socio = padron.get(digitos) or padron.get(wa_id) or {}

            nombre_wa = f.get("wa_name") or f.get("wa_name_entrante") or ""
            nombre_socio = socio.get("nombre") or ""

            # Priorizar el nombre de perfil de WhatsApp para coincidir con la base/APEX,
            # y conservar los datos del socio vinculado para enriquecer la vista.
            nombre_mostrado = nombre_wa or nombre_socio or f"+{wa_id}"
            ultimo_entrante_id = f.get("ultimo_entrante_id")
            ultimo_saliente_id = f.get("ultimo_saliente_id") or 0

            # Se considera pendiente si el último mensaje entrante no tiene respuesta posterior
            tiene_entrantes = (f.get("total_entrantes") or 0) > 0
            if ultimo_entrante_id:
                pendiente = ultimo_entrante_id > ultimo_saliente_id
            else:
                pendiente = False

            # Cálculo de ventana de 24 horas
            ventana_24h_activa = False
            fecha_entrante = f.get("ultima_fecha_entrante")
            if fecha_entrante:
                try:
                    if isinstance(fecha_entrante, datetime):
                        dt_entrante = fecha_entrante
                        if dt_entrante.tzinfo is not None:
                            dt_entrante = dt_entrante.replace(tzinfo=None)
                    else:
                        limpia = str(fecha_entrante).split(".")[0].replace("T", " ")
                        dt_entrante = datetime.strptime(limpia, "%Y-%m-%d %H:%M:%S")
                    segundos_transcurridos = (datetime.now() - dt_entrante).total_seconds()
                    ventana_24h_activa = (0 <= segundos_transcurridos <= 86400)
                except Exception:
                    ventana_24h_activa = False

            ultimo_texto = f.get("ultimo_texto") or ""
            ultimo_estado = f.get("ultimo_estado")
            if not ultimo_estado:
                if f.get("ultimo_tipo") == "status":
                    ultimo_estado = ultimo_texto
                elif f.get("ultima_direccion") == "ENTRANTE":
                    ultimo_estado = "RECIBIDO"
                else:
                    ultimo_estado = "sent"

            item = {
                "wa_id": wa_id,
                "nombre": nombre_mostrado,
                "nombre_wa": f.get("wa_name") or "",
                "es_socio": bool(socio),
                "socio_datos": socio,
                "total_mensajes": f.get("total_mensajes") or 0,
                "total_entrantes": f.get("total_entrantes") or 0,
                "tiene_entrantes": tiene_entrantes,
                "pendiente": pendiente,
                "ventana_24h_activa": ventana_24h_activa,
                "ultimo_mensaje": {
                    "id_log": f.get("ultimo_id"),
                    "direccion": f.get("ultima_direccion"),
                    "tipo": f.get("ultimo_tipo"),
                    "texto": ultimo_texto,
                    "estado": ultimo_estado,
                    "fecha": str(f.get("ultima_fecha") or ""),
                },
            }

            # Filtros
            if filtro_str == "pendientes" and not pendiente:
                continue
            if filtro_str == "recibidos" and not tiene_entrantes:
                continue

            # Búsqueda
            if termino:
                buscables = f"{wa_id} {nombre_mostrado} {f.get('wa_name') or ''} {socio.get('matricula', '')} {socio.get('dni', '')} {ultimo_texto}".lower()
                if termino not in buscables:
                    continue

            conversaciones.append(item)

        return conversaciones

    @classmethod
    def obtener_conversacion(cls, wa_id: str) -> dict:
        """
        Retorna el historial completo de mensajes con un contacto/socio,
        ordenado cronológicamente, con trazabilidad de entregas y datos de perfil.
        """
        padron = _obtener_padron_socios()
        digitos = re.sub(r"\D", "", str(wa_id))
        socio = padron.get(digitos) or padron.get(wa_id) or {}

        wa_id_limpio = digitos
        wa_id_con_mas = f"+{wa_id_limpio}" if wa_id_limpio else wa_id

        sql_mensajes = """
            SELECT 
                id_log,
                wa_id,
                wa_name,
                wsp_msg_id,
                direccion,
                tipo_mensaje,
                texto_mensaje,
                file_id,
                estado_status,
                fecha_registro
            FROM wsp_log_mensajes
            WHERE wa_id = :w1 OR wa_id = :w2 OR wa_id = :w3
            ORDER BY id_log ASC
        """

        filas = DBManager.execute_query(sql_mensajes, sql_mensajes, {
            "w1": wa_id,
            "w2": wa_id_limpio,
            "w3": wa_id_con_mas,
        })

        # Mapear estados de entrega por wsp_msg_id para salientes
        estados_por_msg_id = {}
        for r in filas:
            if r.get("direccion") == "SALIENTE" and r.get("tipo_mensaje") == "status":
                msg_id = r.get("wsp_msg_id")
                st = (r.get("texto_mensaje") or r.get("estado_status") or "").lower()
                if msg_id:
                    # Jerarquía de estados: read > delivered > sent
                    prioridades = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
                    actual = estados_por_msg_id.get(msg_id, "sent")
                    if prioridades.get(st, 0) >= prioridades.get(actual, 0):
                        estados_por_msg_id[msg_id] = st

        mensajes_procesados = []
        ultima_fecha_entrante = None
        ultimo_entrante_id = None
        ultimo_saliente_id = None

        for r in filas:
            dir_msg = r.get("direccion")
            tipo = r.get("tipo_mensaje")
            msg_id = r.get("wsp_msg_id")

            # Actualizar trackers de última interacción
            if dir_msg == "ENTRANTE":
                ultimo_entrante_id = r.get("id_log")
                f_reg = r.get("fecha_registro")
                if f_reg:
                    ultima_fecha_entrante = f_reg
            elif dir_msg == "SALIENTE" and tipo != "status":
                ultimo_saliente_id = r.get("id_log")

            # Determinar estado de confirmación para salientes
            estado_entrega = r.get("estado_status") or "sent"
            if msg_id and msg_id in estados_por_msg_id:
                estado_entrega = estados_por_msg_id[msg_id]

            mensajes_procesados.append({
                "id_log": r.get("id_log"),
                "direccion": dir_msg,
                "tipo": tipo,
                "texto": r.get("texto_mensaje") or "",
                "file_id": r.get("file_id"),
                "wsp_msg_id": msg_id or "",
                "estado_status": estado_entrega,
                "fecha": str(r.get("fecha_registro") or ""),
            })

        # Evaluación ventana de 24 horas
        ventana_24h_activa = False
        tiempo_restante_texto = "Ventana cerrada"
        if ultima_fecha_entrante:
            try:
                limpia = str(ultima_fecha_entrante).split(".")[0].replace("T", " ")
                dt_entrante = datetime.strptime(limpia, "%Y-%m-%d %H:%M:%S")
                segundos = (datetime.now() - dt_entrante).total_seconds()
                if 0 <= segundos <= 86400:
                    ventana_24h_activa = True
                    horas_restantes = int((86400 - segundos) // 3600)
                    min_restantes = int(((86400 - segundos) % 3600) // 60)
                    tiempo_restante_texto = f"{horas_restantes}h {min_restantes}m restantes"
            except Exception:
                ventana_24h_activa = False

        wa_name_entrante = None
        for r in reversed(filas):
            if r.get("wa_name"):
                wa_name_entrante = r.get("wa_name")
                break

        nombre_contacto = wa_name_entrante or socio.get("nombre") or f"+{wa_id}"
        pendiente = (ultimo_entrante_id is not None) and (ultimo_entrante_id > (ultimo_saliente_id or 0))

        return {
            "wa_id": wa_id,
            "nombre": nombre_contacto,
            "es_socio": bool(socio),
            "socio_datos": socio,
            "pendiente": pendiente,
            "ventana_24h_activa": ventana_24h_activa,
            "tiempo_restante_24h": tiempo_restante_texto,
            "mensajes": mensajes_procesados,
        }

    @classmethod
    def enviar_respuesta(
        cls,
        wa_id: str,
        texto: str,
        usuario_actual: str = "operador",
        wsp_msg_id_contexto: Optional[str] = None,
        tipo_envio: str = "texto",
        nombre_plantilla: Optional[str] = None,
        parametros_plantilla: Optional[dict] = None,
    ) -> dict:
        """
        Envía un mensaje de respuesta a través de la WhatsApp Cloud API y
        lo persiste en wsp_log_mensajes.
        """
        wa_id_limpio = re.sub(r"\D", "", str(wa_id))
        if not wa_id_limpio:
            return {"ok": False, "error": "Número de WhatsApp de destino inválido"}

        padron = _obtener_padron_socios()
        socio = padron.get(wa_id_limpio) or {}
        nombre_destinatario = socio.get("nombre") or ""

        # Modo 1: Mensaje de Texto Libre (Atención 24h)
        if tipo_envio == "texto":
            cuerpo = (texto or "").strip()
            if not cuerpo:
                return {"ok": False, "error": "El mensaje de respuesta no puede estar vacío"}

            exito, detalle = enviar_mensaje_texto(
                numero_destino=wa_id_limpio,
                texto=cuerpo,
                access_token=META_ACCESS_TOKEN,
                phone_number_id=META_PHONE_NUMBER_ID,
                mensaje_contexto_id=wsp_msg_id_contexto,
            )

            if not exito:
                es_24h = "24 horas" in detalle or "131047" in detalle
                return {
                    "ok": False,
                    "error": detalle,
                    "es_error_24h": es_24h,
                }

            wsp_msg_id = detalle
            tipo_msg_log = "text"
            texto_guardar = cuerpo

        # Modo 2: Envío de Plantilla Aprobada por Meta
        elif tipo_envio == "plantilla":
            if not nombre_plantilla:
                return {"ok": False, "error": "Debes especificar la plantilla a enviar"}

            plantilla_cfg = PLANTILLAS_CONFIG.get(nombre_plantilla)
            if not plantilla_cfg:
                return {"ok": False, "error": f"Plantilla '{nombre_plantilla}' no registrada"}

            params = {}
            for k, v in (parametros_plantilla or {}).items():
                params[k] = limpiar_parametro(v)

            # Auto-completar nombre si no viene y se conoce
            if "nombre" in plantilla_cfg.get("variables", []) and not params.get("nombre") and nombre_destinatario:
                params["nombre"] = limpiar_parametro(nombre_destinatario)

            exito, detalle = enviar_plantilla(
                numero_destino=f"+{wa_id_limpio}",
                nombre_plantilla=nombre_plantilla,
                parametros=params,
                access_token=META_ACCESS_TOKEN,
                phone_number_id=META_PHONE_NUMBER_ID,
                idioma=plantilla_cfg.get("idioma", "es_AR"),
            )

            if not exito:
                return {"ok": False, "error": detalle}

            wsp_msg_id = detalle
            tipo_msg_log = "template"
            texto_guardar = PlantillasService.renderizar_previsualizacion(nombre_plantilla, params)

        else:
            return {"ok": False, "error": f"Tipo de envío '{tipo_envio}' no soportado"}

        # Registrar el mensaje saliente en wsp_log_mensajes
        payload_audit = json.dumps({
            "enviado_por": usuario_actual,
            "tipo_envio": tipo_envio,
            "contexto_id": wsp_msg_id_contexto,
            "plantilla": nombre_plantilla if tipo_envio == "plantilla" else None,
        }, ensure_ascii=False)

        sql_or = """
            INSERT INTO wsp_log_mensajes (
                wa_id, wa_name, wsp_msg_id, direccion, tipo_mensaje,
                texto_mensaje, json_puro, estado_status, fecha_registro
            ) VALUES (
                :wa_id, :wa_name, :wsp_msg_id, 'SALIENTE', :tipo_mensaje,
                :texto_mensaje, :json_puro, 'sent', SYSTIMESTAMP
            )
        """
        sql_sq = """
            INSERT INTO wsp_log_mensajes (
                wa_id, wa_name, wsp_msg_id, direccion, tipo_mensaje,
                texto_mensaje, json_puro, estado_status, fecha_registro
            ) VALUES (
                :wa_id, :wa_name, :wsp_msg_id, 'SALIENTE', :tipo_mensaje,
                :texto_mensaje, :json_puro, 'sent', CURRENT_TIMESTAMP
            )
        """
        try:
            DBManager.execute_update(sql_or, sql_sq, {
                "wa_id": wa_id_limpio,
                "wa_name": nombre_destinatario,
                "wsp_msg_id": wsp_msg_id,
                "tipo_mensaje": tipo_msg_log,
                "texto_mensaje": texto_guardar,
                "json_puro": payload_audit,
            })
        except Exception as e:
            logger.error("Error registrando mensaje saliente en wsp_log_mensajes: %s", e)

        return {
            "ok": True,
            "wsp_msg_id": wsp_msg_id,
            "texto": texto_guardar,
            "mensaje": "Mensaje enviado exitosamente vía WhatsApp Cloud API",
        }
