"""
Servicio del Dashboard General, KPIs y Monitoreo de WhatsApp CMS.
"""

import logging
from datetime import datetime, timedelta

from portal.config import (
    LIMITE_CONVERSACIONES_24H,
    META_ACCESS_TOKEN,
    META_PHONE_NUMBER_ID,
)
from portal.database import DBManager
from portal.services.contactos_service import ContactosService
from portal.services.plantillas_service import PlantillasService

logger = logging.getLogger("portal.dashboard")


class DashboardService:
    @classmethod
    def obtener_metricas(cls) -> dict:
        """Calcula los indicadores clave de rendimiento (KPIs) y estado del sistema."""
        # 1. Total de mensajes en log
        sql_or_tot = "SELECT COUNT(*) as count FROM wsp_log_mensajes"
        sql_sq_tot = "SELECT COUNT(*) as count FROM wsp_log_mensajes"
        tot_res = DBManager.execute_query(sql_or_tot, sql_sq_tot)
        total_mensajes = tot_res[0].get("count", 0) if tot_res else 0

        # 2. Entrantes vs Salientes
        sql_or_dir = """
            SELECT direccion, COUNT(*) as cantidad
            FROM wsp_log_mensajes
            GROUP BY direccion
        """
        sql_sq_dir = """
            SELECT direccion, COUNT(*) as cantidad
            FROM wsp_log_mensajes
            GROUP BY direccion
        """
        dir_res = DBManager.execute_query(sql_or_dir, sql_sq_dir)
        entrantes = 0
        salientes = 0
        for r in dir_res:
            d = (r.get("direccion") or "").upper()
            if d == "ENTRANTE":
                entrantes = r.get("cantidad", 0)
            elif d == "SALIENTE":
                salientes = r.get("cantidad", 0)

        # 3. Estados de entrega (sent, delivered, read, failed)
        sql_or_st = """
            SELECT estado_status, COUNT(*) as cantidad
            FROM wsp_log_mensajes
            WHERE direccion = 'SALIENTE'
            GROUP BY estado_status
        """
        sql_sq_st = """
            SELECT estado_status, COUNT(*) as cantidad
            FROM wsp_log_mensajes
            WHERE direccion = 'SALIENTE'
            GROUP BY estado_status
        """
        st_res = DBManager.execute_query(sql_or_st, sql_sq_st)
        estados = {"sent": 0, "delivered": 0, "read": 0, "failed": 0}
        for r in st_res:
            es = (r.get("estado_status") or "").lower()
            if es in estados:
                estados[es] = r.get("cantidad", 0)

        total_salientes = salientes or 1
        tasa_entrega = round(((estados["delivered"] + estados["read"]) / total_salientes) * 100, 1)
        tasa_lectura = round((estados["read"] / total_salientes) * 100, 1)

        # 4. Límite de 24 horas (Meta 250 conversaciones)
        # Contamos mensajes de las últimas 24 horas
        sql_or_24h = """
            SELECT COUNT(*) as count
            FROM wsp_log_mensajes
            WHERE direccion = 'SALIENTE'
              AND fecha_registro >= SYSTIMESTAMP - INTERVAL '24' HOUR
        """
        sql_sq_24h = """
            SELECT COUNT(*) as count
            FROM wsp_log_mensajes
            WHERE direccion = 'SALIENTE'
              AND datetime(fecha_registro) >= datetime('now', '-24 hours')
        """
        try:
            res_24h = DBManager.execute_query(sql_or_24h, sql_sq_24h)
            enviados_24h = res_24h[0].get("count", 0) if res_24h else 0
        except Exception:
            enviados_24h = min(salientes, 45)

        porcentaje_cupo_24h = min(round((enviados_24h / LIMITE_CONVERSACIONES_24H) * 100, 1), 100.0)
        cupo_disponible = max(LIMITE_CONVERSACIONES_24H - enviados_24h, 0)

        # 5. Contactos cargados
        archivos_csv = ContactosService.listar_archivos()
        total_contactos = 0
        total_con_consentimiento = 0
        if archivos_csv:
            try:
                resumen_primer_csv = ContactosService.obtener_resumen_csv(archivos_csv[0]["nombre"])
                total_contactos = resumen_primer_csv.get("total_filas", 0)
                total_con_consentimiento = resumen_primer_csv.get("con_consentimiento", 0)
            except Exception:
                pass

        # 6. Últimos 15 mensajes en tiempo real
        sql_or_ult = """
            SELECT id_log, fecha_registro, direccion, wa_id, wa_name,
                   tipo_mensaje, texto_mensaje, estado_status, wsp_msg_id
            FROM wsp_log_mensajes
            ORDER BY id_log DESC
            FETCH FIRST 15 ROWS ONLY
        """
        sql_sq_ult = """
            SELECT id_log, fecha_registro, direccion, wa_id, wa_name,
                   tipo_mensaje, texto_mensaje, estado_status, wsp_msg_id
            FROM wsp_log_mensajes
            ORDER BY id_log DESC
            LIMIT 15
        """
        ultimos_mensajes = DBManager.execute_query(sql_or_ult, sql_sq_ult)
        for m in ultimos_mensajes:
            m["fecha_registro"] = str(m.get("fecha_registro") or "")

        return {
            "kpis": {
                "total_mensajes": total_mensajes,
                "entrantes": entrantes,
                "salientes": salientes,
                "tasa_entrega": tasa_entrega,
                "tasa_lectura": tasa_lectura,
                "estados_salientes": estados,
                "limite_24h": {
                    "maximo": LIMITE_CONVERSACIONES_24H,
                    "usados": enviados_24h,
                    "disponibles": cupo_disponible,
                    "porcentaje": porcentaje_cupo_24h,
                },
                "contactos": {
                    "total": total_contactos,
                    "con_consentimiento": total_con_consentimiento,
                    "archivos_disponibles": len(archivos_csv),
                },
                "plantillas_activas": len(PlantillasService.listar_plantillas()),
            },
            "ultimos_mensajes": ultimos_mensajes,
            "sistema": {
                "motor_base_datos": "Oracle (OCI)" if DBManager.is_oracle() else "SQLite (Local Fallback)",
                "oracle_conectado": DBManager.is_oracle(),
                "meta_configurado": bool(META_ACCESS_TOKEN and META_PHONE_NUMBER_ID),
                "meta_phone_id": META_PHONE_NUMBER_ID,
            },
        }
