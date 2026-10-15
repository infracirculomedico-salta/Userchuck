"""
Servicio de Gestión y Normalización de Contactos y Padrón de Socios CMS.
"""

import csv
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from portal.config import CONTACTOS_DIR, PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "sender"))
try:
    from contactos import (
        COLUMNAS_ESPERADAS,
        _detectar_separador,
        _leer_texto,
    )
    from normalizar import normalizar_numero_con_motivo
except ImportError:
    COLUMNAS_ESPERADAS = [
        "FECHA", "MAIL", "APEYNOM", "DNI", "MATRICULA", "WHATSAPP", "ESTADO_CONSENTIMIENTO"
    ]
    def normalizar_numero_con_motivo(n):
        return n, ""

logger = logging.getLogger("portal.contactos")


class ContactosService:
    @classmethod
    def listar_archivos(cls) -> list[dict]:
        """Lista todos los archivos CSV en la carpeta de contactos."""
        archivos = []
        if not CONTACTOS_DIR.exists():
            return []

        for p in sorted(CONTACTOS_DIR.glob("*.csv")):
            stat = p.stat()
            archivos.append({
                "nombre": p.name,
                "tamano_bytes": stat.st_size,
                "tamano_kb": round(stat.st_size / 1024, 1),
                "fecha_modificacion": stat.st_mtime,
            })
        return archivos

    @classmethod
    def obtener_resumen_csv(cls, nombre_archivo: str) -> dict:
        """Lee el CSV y devuelve estadísticas de contactos y consentimiento."""
        ruta = CONTACTOS_DIR / nombre_archivo
        if not ruta.exists():
            raise FileNotFoundError(f"Archivo {nombre_archivo} no encontrado")

        contenido, encoding = _leer_texto(ruta)
        lineas = contenido.splitlines()
        if not lineas:
            return {"error": "El archivo está vacío"}

        separador = _detectar_separador(lineas[0])
        lector = csv.DictReader(lineas, delimiter=separador)
        columnas = lector.fieldnames or []

        total = 0
        con_consentimiento = 0
        excluidos_consentimiento = 0
        telefonos_validos = 0
        telefonos_invalidos = 0
        columnas_variables = [
            c for c in columnas if c and c.upper() not in COLUMNAS_ESPERADAS
        ]

        for fila in lector:
            total += 1
            estado = (fila.get("ESTADO_CONSENTIMIENTO") or "").strip().upper()
            if estado == "ACEPTO":
                con_consentimiento += 1
                tel_crudo = fila.get("WHATSAPP")
                norm, motivo = normalizar_numero_con_motivo(tel_crudo)
                if norm:
                    telefonos_validos += 1
                else:
                    telefonos_invalidos += 1
            else:
                excluidos_consentimiento += 1

        return {
            "archivo": nombre_archivo,
            "encoding": encoding,
            "separador": separador,
            "columnas": columnas,
            "columnas_variables": columnas_variables,
            "total_filas": total,
            "con_consentimiento": con_consentimiento,
            "excluidos_consentimiento": excluidos_consentimiento,
            "telefonos_validos": telefonos_validos,
            "telefonos_invalidos": telefonos_invalidos,
            "aptos_para_envio": telefonos_validos,
        }

    @classmethod
    def leer_filas_csv(
        cls,
        nombre_archivo: str,
        filtro_consentimiento: Optional[str] = None,
        busqueda: Optional[str] = None,
        limite: int = 200,
        offset: int = 0,
    ) -> dict:
        """Devuelve contactos con paginación, filtros y normalización de teléfonos."""
        ruta = CONTACTOS_DIR / nombre_archivo
        if not ruta.exists():
            raise FileNotFoundError(f"Archivo {nombre_archivo} no encontrado")

        contenido, encoding = _leer_texto(ruta)
        lineas = contenido.splitlines()
        if not lineas:
            return {"contactos": [], "total": 0}

        separador = _detectar_separador(lineas[0])
        lector = csv.DictReader(lineas, delimiter=separador)
        columnas = lector.fieldnames or []

        todos = []
        termino = busqueda.lower().strip() if busqueda else None

        for idx, fila in enumerate(lector, 1):
            estado = (fila.get("ESTADO_CONSENTIMIENTO") or "").strip().upper()
            if filtro_consentimiento and estado != filtro_consentimiento.upper():
                continue

            nombre = fila.get("APEYNOM", "")
            dni = fila.get("DNI", "")
            matricula = fila.get("MATRICULA", "")
            tel_crudo = fila.get("WHATSAPP", "")
            mail = fila.get("MAIL", "")

            if termino:
                texto_busqueda = f"{nombre} {dni} {matricula} {tel_crudo} {mail}".lower()
                if termino not in texto_busqueda:
                    continue

            norm, motivo = normalizar_numero_con_motivo(tel_crudo)

            contacto = {
                "fila": idx,
                "nombre": nombre,
                "dni": dni,
                "matricula": matricula,
                "email": mail,
                "telefono_original": tel_crudo,
                "telefono_normalizado": norm,
                "motivo_telefono": motivo,
                "telefono_valido": norm is not None,
                "consentimiento": estado,
                "fecha": fila.get("FECHA", ""),
                "extras": {k: fila.get(k, "") for k in columnas if k.upper() not in COLUMNAS_ESPERADAS},
            }
            todos.append(contacto)

        total_filtrados = len(todos)
        paginados = todos[offset : offset + limite]

        return {
            "archivo": nombre_archivo,
            "columnas": columnas,
            "total": total_filtrados,
            "offset": offset,
            "limite": limite,
            "contactos": paginados,
        }

    @classmethod
    def guardar_archivo_csv(cls, nombre: str, contenido_bytes: bytes) -> str:
        """Guarda un archivo CSV subido por el usuario con validación de columnas."""
        nombre_limpio = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", nombre)
        if not nombre_limpio.lower().endswith(".csv"):
            nombre_limpio += ".csv"

        ruta_destino = CONTACTOS_DIR / nombre_limpio
        ruta_destino.write_bytes(contenido_bytes)

        # Validar columnas
        try:
            contenido, _ = _leer_texto(ruta_destino)
            primera_linea = contenido.splitlines()[0]
            sep = _detectar_separador(primera_linea)
            columnas = [c.strip().upper() for c in primera_linea.split(sep)]
            faltantes = [c for c in COLUMNAS_ESPERADAS if c not in columnas]
            if faltantes:
                ruta_destino.unlink(missing_ok=True)
                raise ValueError(f"Faltan columnas obligatorias: {faltantes}")
        except Exception as e:
            ruta_destino.unlink(missing_ok=True)
            raise e

        return nombre_limpio
