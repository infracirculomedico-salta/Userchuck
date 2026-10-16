"""
Capa de datos y base de datos para el Portal de WhatsApp.
Soporta Oracle en producción (OCI) y SQLite como fallback automático en desarrollo local.
"""

import csv
import hashlib
import logging
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import oracledb

from portal.config import (
    DB_DSN,
    DB_PASSWORD,
    DB_SCHEMA,
    DB_USER,
    ORACLE_LIB_DIR,
    PORTAL_DIR,
    PROJECT_ROOT,
)

logger = logging.getLogger("portal.db")

# Archivo de base de datos local SQLite (fallback)
SQLITE_DB_PATH = PORTAL_DIR / "portal_local.db"
RESPALDO_CSV = PROJECT_ROOT / "webhook" / "respaldo_wsp_log_mensajes_20260916_155256.csv"

_cliente_oracle_inicializado = False
_oracle_disponible = None


def _intentar_init_oracle():
    """Intenta inicializar el cliente thick de Oracle si el lib_dir existe."""
    global _cliente_oracle_inicializado
    if _cliente_oracle_inicializado:
        return
    if os.path.exists(ORACLE_LIB_DIR):
        try:
            oracledb.init_oracle_client(lib_dir=ORACLE_LIB_DIR)
            logger.info("Oracle Client inicializado en %s", ORACLE_LIB_DIR)
        except Exception as e:
            logger.warning("No se pudo inicializar Oracle Client en %s: %s", ORACLE_LIB_DIR, e)
    _cliente_oracle_inicializado = True


def verificar_conexion_oracle() -> bool:
    """Verifica si la base de datos Oracle en OCI está accesible."""
    global _oracle_disponible
    if _oracle_disponible is not None:
        return _oracle_disponible

    _intentar_init_oracle()
    try:
        # Timeout corto para no congelar la app si no hay ruta de red a 10.1.0.132
        conn = oracledb.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=DB_DSN,
            tcp_connect_timeout=2.0,
        )
        with conn.cursor() as cur:
            if DB_SCHEMA:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {DB_SCHEMA}")
            cur.execute("SELECT 1 FROM dual")
        conn.close()
        _oracle_disponible = True
        logger.info("Conexión a Oracle OK (OCI) - Usuario: %s, Esquema: %s", DB_USER, DB_SCHEMA)
    except Exception as e:
        _oracle_disponible = False
        logger.info("Oracle no disponible localmente (%s). Se usará SQLite local.", e)

    return _oracle_disponible


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Genera hash seguro PBKDF2 HMAC SHA-256."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    ).hex()
    return pw_hash, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Valida contraseña contra hash almacenado."""
    actual_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(actual_hash, expected_hash)


def _inicializar_sqlite():
    """Crea tablas locales en SQLite si no existen y precarga datos iniciales."""
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # Tabla de mensajes (espejo de wsp_log_mensajes de Oracle)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wsp_log_mensajes (
                id_log INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_id TEXT,
                wa_name TEXT,
                wsp_msg_id TEXT,
                direccion TEXT,
                tipo_mensaje TEXT,
                texto_mensaje TEXT,
                file_id TEXT,
                json_puro TEXT,
                estado_status TEXT,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla de inbox crudo (espejo de wsp_raw_inbox de Oracle)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wsp_raw_inbox (
                id_raw INTEGER PRIMARY KEY AUTOINCREMENT,
                load_json TEXT,
                ip_origen TEXT,
                headers_http TEXT,
                estado_proceso TEXT DEFAULT 'PENDIENTE',
                mensaje_error TEXT,
                fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_proceso TIMESTAMP
            )
        """)

        # Tabla de usuarios del portal
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wsp_usuarios (
                id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                nombre_completo TEXT NOT NULL,
                email TEXT,
                rol TEXT NOT NULL DEFAULT 'OPERADOR',
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                ultimo_acceso TIMESTAMP,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla de campañas de envío
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wsp_campanas (
                id_campana INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                plantilla TEXT NOT NULL,
                archivo_csv TEXT NOT NULL,
                total_contactos INTEGER DEFAULT 0,
                enviados INTEGER DEFAULT 0,
                exitosos INTEGER DEFAULT 0,
                errores INTEGER DEFAULT 0,
                omitidos INTEGER DEFAULT 0,
                estado TEXT DEFAULT 'CREADA',
                log_archivo TEXT,
                creado_por TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_finalizacion TIMESTAMP
            )
        """)

        # Tabla de contactos padrón
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wsp_contactos (
                id_contacto INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula TEXT,
                dni TEXT,
                nombre_completo TEXT NOT NULL,
                email TEXT,
                telefono_original TEXT,
                telefono_normalizado TEXT,
                estado_consentimiento TEXT DEFAULT 'ACEPTO',
                fecha_consentimiento TEXT,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

        # Sembrar usuarios por defecto si no existen
        cursor.execute("SELECT COUNT(*) FROM wsp_usuarios")
        if cursor.fetchone()[0] == 0:
            admin_hash, admin_salt = hash_password("admin123")
            operador_hash, operador_salt = hash_password("operador123")

            cursor.execute("""
                INSERT INTO wsp_usuarios (username, nombre_completo, email, rol, password_hash, password_salt, activo)
                VALUES ('admin', 'Administrador General CMS', 'admin@cirmedsa.org.ar', 'ADMIN', ?, ?, 1)
            """, (admin_hash, admin_salt))

            cursor.execute("""
                INSERT INTO wsp_usuarios (username, nombre_completo, email, rol, password_hash, password_salt, activo)
                VALUES ('operador', 'Operador de Comunicaciones', 'operador@cirmedsa.org.ar', 'OPERADOR', ?, ?, 1)
            """, (operador_hash, operador_salt))

            conn.commit()
            logger.info("Usuarios por defecto creados: admin (admin123), operador (operador123)")

        # Precargar datos de respaldo si wsp_log_mensajes está vacía
        cursor.execute("SELECT COUNT(*) FROM wsp_log_mensajes")
        if cursor.fetchone()[0] == 0 and RESPALDO_CSV.exists():
            try:
                with open(RESPALDO_CSV, mode="r", encoding="utf-8") as f:
                    lector = csv.DictReader(f)
                    filas = []
                    for r in lector:
                        filas.append((
                            r.get("ID_LOG"),
                            r.get("WA_ID"),
                            r.get("WA_NAME"),
                            r.get("WSP_MSG_ID"),
                            r.get("DIRECCION"),
                            r.get("TIPO_MENSAJE"),
                            r.get("TEXTO_MENSAJE"),
                            r.get("FILE_ID"),
                            r.get("JSON_PURO"),
                            r.get("TEXTO_MENSAJE") if r.get("TIPO_MENSAJE") == "status" else "RECIBIDO",
                            r.get("FECHA_REGISTRO"),
                        ))
                    cursor.executemany("""
                        INSERT OR REPLACE INTO wsp_log_mensajes (
                            id_log, wa_id, wa_name, wsp_msg_id, direccion,
                            tipo_mensaje, texto_mensaje, file_id, json_puro,
                            estado_status, fecha_registro
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, filas)
                    conn.commit()
                    logger.info("Precargados %d mensajes de respaldo en wsp_log_mensajes", len(filas))
            except Exception as ex:
                logger.warning("No se pudo precargar respaldo_wsp_log_mensajes: %s", ex)


# Inicializar base SQLite al cargar módulo
_inicializar_sqlite()


class DBManager:
    """Manejador unificado de consultas para Oracle y SQLite."""

    @classmethod
    def is_oracle(cls) -> bool:
        return verificar_conexion_oracle()

    @classmethod
    @contextmanager
    def get_connection(cls):
        """Retorna conexión activa y maneja transacciones."""
        if cls.is_oracle():
            conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
            if DB_SCHEMA:
                with conn.cursor() as cur:
                    cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {DB_SCHEMA}")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @staticmethod
    def _adaptar_params_oracle(sql: str, params: dict | tuple | list):
        """Si la consulta Oracle usa variables nombradas (:nom) y se pasó una tupla, mapea por orden."""
        if isinstance(params, dict):
            return params
        if isinstance(params, (tuple, list)):
            vars_in_sql = []
            for match in re.finditer(r":([a-zA-Z0-9_]+)", sql):
                v = match.group(1)
                if v not in vars_in_sql:
                    vars_in_sql.append(v)
            if vars_in_sql and len(vars_in_sql) == len(params):
                return dict(zip(vars_in_sql, params))
        return params

    @classmethod
    def execute_query(cls, sql_oracle: str, sql_sqlite: str, params: dict | tuple = ()):
        """Ejecuta consulta según motor y devuelve lista de diccionarios."""
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            if cls.is_oracle():
                p = cls._adaptar_params_oracle(sql_oracle, params)
                cursor.execute(sql_oracle, p)
                columnas = [col[0].lower() for col in cursor.description]
                filas = cursor.fetchall()
                resultado = []
                for fila in filas:
                    d = {}
                    for col, val in zip(columnas, fila):
                        # Manejo de CLOBs de Oracle
                        d[col] = val.read() if hasattr(val, "read") else val
                    resultado.append(d)
                return resultado
            else:
                p = params
                cursor.execute(sql_sqlite, p)
                filas = cursor.fetchall()
                return [dict(f) for f in filas]

    @classmethod
    def execute_update(cls, sql_oracle: str, sql_sqlite: str, params: dict | tuple = ()):
        """Ejecuta INSERT/UPDATE/DELETE."""
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            if cls.is_oracle():
                p = cls._adaptar_params_oracle(sql_oracle, params)
                cursor.execute(sql_oracle, p)
            else:
                cursor.execute(sql_sqlite, params)
            return cursor.rowcount
