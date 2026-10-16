"""
Acceso a Oracle para el webhook de WhatsApp Business API.

Reutiliza el mismo patrón de conexión que testoracle.py (init_oracle_client
con el cliente instant client 21 en modo thick) y las credenciales de
config/database.env (DB_USER, DB_PASSWORD, DB_DSN).

Todas las funciones públicas atrapan las excepciones de oracledb y las
loguean: un problema de base de datos nunca debe tirar abajo el proceso
principal del webhook (ver main.py, que necesita responder 200 a Meta
siempre que la firma sea válida).
"""

import logging
import os
from pathlib import Path

import oracledb

logger = logging.getLogger("webhook.db")

CONFIG_DIR = Path("/opt/userchuck/config")
ORACLE_LIB_DIR = "/usr/lib/oracle/21/client64/lib"

# init_oracle_client debe llamarse una sola vez por proceso.
_cliente_inicializado = False

# Pool de conexiones, creado a demanda y compartido por todo el proceso.
# Sin pool, un solo POST de Meta con tres statuses abre cinco conexiones
# nuevas (guardar_raw + tres guardar_log_mensaje + marcar_procesado), y
# cada una es un handshake completo del cliente thick. Esa latencia hace
# que Meta no reciba el 200 a tiempo y reenvíe el evento.
_pool = None

# Tamaño del pool. El webhook atiende un evento por vez y no necesita
# más, pero deja margen para los reintentos solapados de Meta.
POOL_MIN = 1
POOL_MAX = 4

# Oracle avisa con ORA-00001 que una fila ya existe según un índice
# único. Para este webhook eso no es un error: significa que Meta
# reenvió un evento que ya habíamos guardado.
ORA_DUPLICADO = 1

# Si la columna estado_status existe, el estado del mensaje se guarda
# también ahí (VARCHAR2) además de en texto_mensaje (CLOB), porque
# Oracle no puede indexar un CLOB y la deduplicación necesita el par
# (wsp_msg_id, estado) en un índice único. Se detecta una vez por
# proceso para que el DDL y el reinicio del webhook no tengan que
# coordinarse: sin la columna, el INSERT sigue siendo el de antes.
_tiene_estado_status = None

# Valor de estado_status para los mensajes entrantes, que no tienen
# "status". Un literal y no NULL a propósito: Oracle no considera
# iguales dos NULL, así que con NULL el índice único dejaría pasar el
# mismo mensaje entrante dos veces.
ESTADO_ENTRANTE = "RECIBIDO"


def _asegurar_cliente_oracle() -> None:
    """Inicializa el cliente Oracle (modo thick) una sola vez por proceso."""
    global _cliente_inicializado
    if _cliente_inicializado:
        return
    try:
        oracledb.init_oracle_client(lib_dir=ORACLE_LIB_DIR)
    except oracledb.ProgrammingError:
        # oracledb lanza ProgrammingError si init_oracle_client ya fue
        # llamado antes en este proceso (por ejemplo, por otro módulo).
        # No es un error real, seguimos.
        pass
    _cliente_inicializado = True


def _asegurar_pool() -> oracledb.ConnectionPool:
    """
    Crea el pool de conexiones la primera vez que se lo necesita.

    Si la creación falla (Oracle caído al arrancar, credenciales mal),
    el pool queda en None y se vuelve a intentar en la llamada siguiente,
    en lugar de dejar el proceso inservible hasta reiniciarlo.
    """
    global _pool
    if _pool is not None:
        return _pool

    _asegurar_cliente_oracle()

    def _init_session(conn, tag):
        schema = os.environ.get("DB_SCHEMA", "sistema")
        if schema:
            with conn.cursor() as cur:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")

    _pool = oracledb.create_pool(
        user=os.environ.get("DB_USER", "sistema"),
        password=os.environ.get("DB_PASSWORD"),
        dsn=os.environ.get("DB_DSN"),
        min=POOL_MIN,
        max=POOL_MAX,
        increment=1,
        session_callback=_init_session,
    )
    logger.info("Pool de conexiones Oracle creado (min=%d, max=%d, schema=%s)", POOL_MIN, POOL_MAX, os.environ.get("DB_SCHEMA", "sistema"))
    return _pool


def obtener_conexion() -> oracledb.Connection:
    """
    Toma una conexión del pool.

    Se usa igual que antes: al cerrarla (o al salir del `with`) la
    conexión vuelve al pool en vez de cerrarse de verdad.

    Puede lanzar oracledb.Error si el pool no se puede crear o no hay
    conexión disponible: quien la use en este módulo la atrapa y loguea,
    sin propagarla al resto del webhook.
    """
    return _asegurar_pool().acquire()


def guardar_raw(payload_json: str, ip_origen: str, headers_json: str) -> int | None:
    """
    Inserta el payload crudo del webhook en wsp_raw_inbox con
    estado_proceso='PENDIENTE'.

    Devuelve el id_raw generado, o None si la inserción falló (el error
    queda logueado, no se propaga).
    """
    try:
        with obtener_conexion() as conexion:
            with conexion.cursor() as cursor:
                id_raw_var = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    """
                    INSERT INTO wsp_raw_inbox (
                        load_json,
                        ip_origen,
                        headers_http,
                        estado_proceso,
                        fecha_ingreso
                    ) VALUES (
                        :load_json,
                        :ip_origen,
                        :headers_http,
                        'PENDIENTE',
                        SYSTIMESTAMP
                    )
                    RETURNING id_raw INTO :id_raw
                    """,
                    load_json=payload_json,
                    ip_origen=ip_origen,
                    headers_http=headers_json,
                    id_raw=id_raw_var,
                )
                conexion.commit()
                id_raw = int(id_raw_var.getvalue()[0])
                logger.info("Payload guardado en wsp_raw_inbox (id_raw=%s)", id_raw)
                return id_raw
    except oracledb.Error:
        logger.exception("Error guardando payload crudo en wsp_raw_inbox")
        return None


def marcar_procesado(id_raw: int, exito: bool, mensaje_error: str | None = None) -> None:
    """
    Actualiza wsp_raw_inbox: estado_proceso a 'PROCESADO' o 'ERROR' según
    `exito`, mensaje_error si corresponde, y fecha_proceso = SYSTIMESTAMP.

    No hace nada si id_raw es None (no se pudo insertar el raw en primer
    lugar). Cualquier error de Oracle queda logueado, no se propaga.
    """
    if id_raw is None:
        return

    estado = "PROCESADO" if exito else "ERROR"
    try:
        with obtener_conexion() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE wsp_raw_inbox
                    SET estado_proceso = :estado,
                        mensaje_error = :mensaje_error,
                        fecha_proceso = SYSTIMESTAMP
                    WHERE id_raw = :id_raw
                    """,
                    estado=estado,
                    mensaje_error=mensaje_error,
                    id_raw=id_raw,
                )
                conexion.commit()
                logger.info("wsp_raw_inbox id_raw=%s marcado como %s", id_raw, estado)
    except oracledb.Error:
        logger.exception("Error actualizando estado_proceso en wsp_raw_inbox (id_raw=%s)", id_raw)


def _detectar_estado_status(conexion) -> bool:
    """
    Averigua una sola vez si wsp_log_mensajes tiene la columna
    estado_status, para adaptar el INSERT sin depender de cuándo se
    corrió el ALTER TABLE.
    """
    global _tiene_estado_status
    if _tiene_estado_status is not None:
        return _tiene_estado_status

    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM user_tab_columns
            WHERE table_name = 'WSP_LOG_MENSAJES' AND column_name = 'ESTADO_STATUS'
            """
        )
        _tiene_estado_status = cursor.fetchone()[0] > 0

    logger.info(
        "wsp_log_mensajes.estado_status %s: la deduplicación por índice único %s",
        "existe" if _tiene_estado_status else "no existe",
        "está activa" if _tiene_estado_status else "NO está activa",
    )
    return _tiene_estado_status


def guardar_log_mensaje(
    wa_id: str | None,
    wa_name: str | None,
    wsp_msg_id: str | None,
    direccion: str,
    tipo_mensaje: str | None,
    texto_mensaje: str | None,
    json_puro: str | None,
    file_id: str | None = None,
) -> int | None:
    """
    Inserta un registro en wsp_log_mensajes.

    Args:
        direccion: 'SALIENTE' para eventos "statuses" (confirmaciones de
            mensajes que nosotros enviamos) o 'ENTRANTE' para mensajes
            que nos escriben los contactos.
        file_id: id del adjunto en los servidores de Meta, para mensajes
            entrantes de tipo image/document/audio/video/sticker. None
            para el resto.

    Returns:
        int | None: el id_log generado; 0 si la fila ya estaba (Meta
        reenvió un evento ya guardado, que no es un error); None si la
        inserción falló de verdad. Quien llama debe distinguir None del
        resto: es la señal de que el mensaje se perdió.
    """
    try:
        with obtener_conexion() as conexion:
            columnas = [
                "wa_id", "wa_name", "wsp_msg_id", "direccion",
                "tipo_mensaje", "texto_mensaje", "file_id", "json_puro",
            ]
            valores = {
                "wa_id": wa_id,
                "wa_name": wa_name,
                "wsp_msg_id": wsp_msg_id,
                "direccion": direccion,
                "tipo_mensaje": tipo_mensaje,
                "texto_mensaje": texto_mensaje,
                "file_id": file_id,
                "json_puro": json_puro,
            }

            if _detectar_estado_status(conexion):
                columnas.append("estado_status")
                valores["estado_status"] = (
                    texto_mensaje if tipo_mensaje == "status" else ESTADO_ENTRANTE
                )

            sql = (
                f"INSERT INTO wsp_log_mensajes ({', '.join(columnas)}, fecha_registro) "
                f"VALUES ({', '.join(':' + c for c in columnas)}, SYSTIMESTAMP) "
                "RETURNING id_log INTO :id_log"
            )

            with conexion.cursor() as cursor:
                id_log_var = cursor.var(oracledb.NUMBER)
                cursor.execute(sql, id_log=id_log_var, **valores)
                conexion.commit()
                id_log = int(id_log_var.getvalue()[0])
                logger.info(
                    "Log de mensaje guardado en wsp_log_mensajes (id_log=%s, direccion=%s)",
                    id_log,
                    direccion,
                )
                return id_log
    except oracledb.IntegrityError as error:
        (detalle,) = error.args
        if getattr(detalle, "code", None) == ORA_DUPLICADO:
            logger.info(
                "Evento ya guardado, se ignora el reenvío de Meta (wsp_msg_id=%s, estado=%s)",
                wsp_msg_id,
                texto_mensaje,
            )
            return 0
        logger.exception("Error guardando mensaje en wsp_log_mensajes (wsp_msg_id=%s)", wsp_msg_id)
        return None
    except oracledb.Error:
        logger.exception("Error guardando mensaje en wsp_log_mensajes (wsp_msg_id=%s)", wsp_msg_id)
        return None
