"""
Servicio de Orquestación, Simulación y Ejecución de Campañas de WhatsApp.
"""

import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from portal.config import (
    CONTACTOS_DIR,
    LIMITE_CONVERSACIONES_24H,
    LOGS_DIR,
    META_ACCESS_TOKEN,
    META_PHONE_NUMBER_ID,
    PROJECT_ROOT,
)
from portal.database import DBManager
from portal.services.plantillas_service import PlantillasService

sys.path.insert(0, str(PROJECT_ROOT / "sender"))
try:
    from contactos import leer_contactos
    from normalizar import normalizar_numero_con_motivo
    from plantillas import (
        COLUMNAS_POR_DEFECTO,
        PLANTILLAS as PLANTILLAS_CONFIG,
        obtener_plantilla,
        resolver_origenes,
    )
    from whatsapp_api import enviar_plantilla, limpiar_parametro
except ImportError:
    PLANTILLAS_CONFIG = {}
    COLUMNAS_POR_DEFECTO = {"nombre": "APEYNOM"}

logger = logging.getLogger("portal.campanas")


class CampanasService:
    @classmethod
    def simular_campana(
        cls,
        nombre_plantilla: str,
        archivo_csv: str,
        columnas_mapeadas: dict,
        valores_fijos: dict,
    ) -> dict:
        """
        Ejecuta la validación y simulación de un envío sin consumir mensajes.
        Devuelve el conteo de destinatarios y previsualización de los primeros mensajes.
        """
        ruta_csv = CONTACTOS_DIR / archivo_csv
        if not ruta_csv.exists():
            return {"ok": False, "error": f"Archivo {archivo_csv} no existe en contactos"}

        try:
            plantilla = obtener_plantilla(nombre_plantilla)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        try:
            origenes = resolver_origenes(plantilla, columnas_mapeadas, valores_fijos)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        try:
            contactos_validos, excluidos_consentimiento = leer_contactos(ruta_csv)
        except Exception as e:
            return {"ok": False, "error": f"Error leyendo CSV: {e}"}

        se_van_a_enviar = 0
        numeros_invalidos = []
        primeros_mensajes = []

        for idx, contacto in enumerate(contactos_validos, 1):
            tel_crudo = contacto.get("WHATSAPP")
            norm, motivo = normalizar_numero_con_motivo(tel_crudo)
            if not norm:
                numeros_invalidos.append({
                    "fila": idx,
                    "nombre": contacto.get("APEYNOM", "Desconocido"),
                    "numero_original": tel_crudo,
                    "motivo": motivo,
                })
                continue

            se_van_a_enviar += 1

            # Construir variables para este contacto
            params = {}
            for var, (tipo, fuente) in origenes.items():
                if tipo == "columna":
                    val = contacto.get(fuente, "")
                else:
                    val = fuente
                params[var] = limpiar_parametro(val)

            if len(primeros_mensajes) < 3:
                mensaje_renderizado = PlantillasService.renderizar_previsualizacion(nombre_plantilla, params)
                primeros_mensajes.append({
                    "destinatario": norm,
                    "nombre": contacto.get("APEYNOM", ""),
                    "variables": params,
                    "texto_renderizado": mensaje_renderizado,
                })

        advertencias = []
        if se_van_a_enviar > LIMITE_CONVERSACIONES_24H:
            advertencias.append(
                f"La campaña supera el límite de {LIMITE_CONVERSACIONES_24H} conversaciones en 24h. "
                "Los mensajes excedentes podrían ser pausados o rechazados por Meta."
            )

        return {
            "ok": True,
            "plantilla": nombre_plantilla,
            "archivo": archivo_csv,
            "total_contactos_con_consentimiento": len(contactos_validos),
            "excluidos_consentimiento": excluidos_consentimiento,
            "numeros_invalidos_total": len(numeros_invalidos),
            "numeros_invalidos_detalle": numeros_invalidos[:10],
            "se_van_a_enviar": se_van_a_enviar,
            "primeros_mensajes": primeros_mensajes,
            "advertencias": advertencias,
        }

    @classmethod
    def ejecutar_campana(
        cls,
        nombre_campana: str,
        nombre_plantilla: str,
        archivo_csv: str,
        columnas_mapeadas: dict,
        valores_fijos: dict,
        usuario_actual: str = "sistema",
        pausa_segundos: float = 0.2,
    ) -> dict:
        """Ejecuta el envío real a los contactos y genera el log de auditoría."""
        simulacion = cls.simular_campana(nombre_plantilla, archivo_csv, columnas_mapeadas, valores_fijos)
        if not simulacion.get("ok"):
            return simulacion

        ruta_csv = CONTACTOS_DIR / archivo_csv
        plantilla = obtener_plantilla(nombre_plantilla)
        origenes = resolver_origenes(plantilla, columnas_mapeadas, valores_fijos)
        contactos_validos, _ = leer_contactos(ruta_csv)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_log = f"envio_{timestamp_str}.csv"
        ruta_log = LOGS_DIR / nombre_log

        exitosos = 0
        errores = 0

        # Crear registro en wsp_campanas
        sql_or_c = """
            INSERT INTO wsp_campanas (nombre, plantilla, archivo_csv, total_contactos, estado, log_archivo, creado_por, fecha_creacion)
            VALUES (:nom, :pl, :csv, :tot, 'EN_PROCESO', :log, :usr, SYSTIMESTAMP)
        """
        sql_sq_c = """
            INSERT INTO wsp_campanas (nombre, plantilla, archivo_csv, total_contactos, estado, log_archivo, creado_por, fecha_creacion)
            VALUES (:nom, :pl, :csv, :tot, 'EN_PROCESO', :log, :usr, CURRENT_TIMESTAMP)
        """
        DBManager.execute_update(sql_or_c, sql_sq_c, {
            "nom": nombre_campana,
            "pl": nombre_plantilla,
            "csv": archivo_csv,
            "tot": simulacion["se_van_a_enviar"],
            "log": nombre_log,
            "usr": usuario_actual,
        })

        # Abrir archivo de log para escribir mensaje por mensaje
        with open(ruta_log, mode="w", newline="", encoding="utf-8") as f_log:
            escritor = csv.writer(f_log)
            escritor.writerow(["plantilla", "nombre", "numero_original", "numero_normalizado", "resultado", "detalle"])

            for contacto in contactos_validos:
                tel_crudo = contacto.get("WHATSAPP")
                norm, motivo = normalizar_numero_con_motivo(tel_crudo)
                if not norm:
                    escritor.writerow([nombre_plantilla, contacto.get("APEYNOM", ""), tel_crudo, "", "ERROR", f"Número inválido: {motivo}"])
                    errores += 1
                    continue

                params = {}
                for var, (tipo, fuente) in origenes.items():
                    val = contacto.get(fuente, "") if tipo == "columna" else fuente
                    params[var] = limpiar_parametro(val)

                # Envío real a Meta Cloud API
                exito, detalle = enviar_plantilla(
                    numero_destino=norm,
                    nombre_plantilla=nombre_plantilla,
                    parametros=params,
                    access_token=META_ACCESS_TOKEN,
                    phone_number_id=META_PHONE_NUMBER_ID,
                    idioma=plantilla.get("idioma", "es_AR"),
                )

                if exito:
                    exitosos += 1
                    resultado_str = "OK"
                else:
                    errores += 1
                    resultado_str = "ERROR"

                escritor.writerow([nombre_plantilla, contacto.get("APEYNOM", ""), tel_crudo, norm, resultado_str, detalle])
                f_log.flush()

                if pausa_segundos > 0:
                    time.sleep(pausa_segundos)

        # Actualizar estado final en wsp_campanas
        estado_final = "COMPLETADA" if errores == 0 else "CON_ERRORES"
        sql_or_up = """
            UPDATE wsp_campanas
            SET enviados = :env, exitosos = :ex, errores = :er, estado = :st, fecha_finalizacion = SYSTIMESTAMP
            WHERE log_archivo = :log
        """
        sql_sq_up = """
            UPDATE wsp_campanas
            SET enviados = :env, exitosos = :ex, errores = :er, estado = :st, fecha_finalizacion = CURRENT_TIMESTAMP
            WHERE log_archivo = :log
        """
        DBManager.execute_update(sql_or_up, sql_sq_up, {
            "env": exitosos + errores,
            "ex": exitosos,
            "er": errores,
            "st": estado_final,
            "log": nombre_log,
        })

        return {
            "ok": True,
            "campana": nombre_campana,
            "plantilla": nombre_plantilla,
            "log_archivo": nombre_log,
            "total_enviados": exitosos + errores,
            "exitosos": exitosos,
            "errores": errores,
            "estado": estado_final,
        }

    @classmethod
    def listar_campanas(cls) -> list[dict]:
        """Obtiene el historial de campañas desde la base de datos y archivos de log."""
        campanas = []

        # 1. Consultar base de datos
        sql_or = """
            SELECT id_campana, nombre, plantilla, archivo_csv, total_contactos,
                   enviados, exitosos, errores, omitidos, estado, log_archivo,
                   creado_por, fecha_creacion, fecha_finalizacion
            FROM wsp_campanas
            ORDER BY id_campana DESC
        """
        sql_sq = """
            SELECT id_campana, nombre, plantilla, archivo_csv, total_contactos,
                   enviados, exitosos, errores, omitidos, estado, log_archivo,
                   creado_por, fecha_creacion, fecha_finalizacion
            FROM wsp_campanas
            ORDER BY id_campana DESC
        """
        filas = DBManager.execute_query(sql_or, sql_sq)
        registrados_logs = {f.get("log_archivo") for f in filas if f.get("log_archivo")}

        for f in filas:
            campanas.append({
                "id": f.get("id_campana"),
                "nombre": f.get("nombre"),
                "plantilla": f.get("plantilla"),
                "archivo_csv": f.get("archivo_csv"),
                "total_contactos": f.get("total_contactos", 0),
                "enviados": f.get("enviados", 0),
                "exitosos": f.get("exitosos", 0),
                "errores": f.get("errores", 0),
                "estado": f.get("estado", "COMPLETADA"),
                "log_archivo": f.get("log_archivo"),
                "creado_por": f.get("creado_por", "sistema"),
                "fecha": str(f.get("fecha_creacion", "")),
            })

        # 2. Descubrir logs en disco que no estén en BD
        if LOGS_DIR.exists():
            for p in sorted(LOGS_DIR.glob("envio_*.csv"), reverse=True):
                if p.name not in registrados_logs:
                    try:
                        with open(p, mode="r", encoding="utf-8") as f:
                            lector = list(csv.DictReader(f))
                            tot = len(lector)
                            ok = sum(1 for r in lector if r.get("resultado") == "OK")
                            err = sum(1 for r in lector if r.get("resultado") == "ERROR")
                            pl = lector[0].get("plantilla", "desconocida") if lector else "desconocida"

                        campanas.append({
                            "id": None,
                            "nombre": f"Envío {p.stem.replace('envio_', '')}",
                            "plantilla": pl,
                            "archivo_csv": "-",
                            "total_contactos": tot,
                            "enviados": tot,
                            "exitosos": ok,
                            "errores": err,
                            "estado": "COMPLETADA" if err == 0 else "CON_ERRORES",
                            "log_archivo": p.name,
                            "creado_por": "CLI",
                            "fecha": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        })
                    except Exception as e:
                        logger.warning("Error leyendo log %s: %s", p.name, e)

        return campanas

    @classmethod
    def ver_log_detalle(cls, nombre_log: str) -> list[dict]:
        """Devuelve las filas detalladas de un archivo de log de envío."""
        ruta = LOGS_DIR / nombre_log
        if not ruta.exists():
            return []

        try:
            with open(ruta, mode="r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except Exception:
            return []
