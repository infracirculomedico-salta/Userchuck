"""
Consulta los logs del webhook de WhatsApp directamente en Oracle.

Sirve para revisar qué llegó sin importar quién levantó el proceso ni
dónde quedó su salida estándar: la base es el registro real.

Uso:
    python ver_logs.py                 # ultimos 20 mensajes (wsp_log_mensajes)
    python ver_logs.py -n 50           # ultimos 50
    python ver_logs.py --entrantes     # solo los mensajes que nos escriben
    python ver_logs.py --salientes     # solo confirmaciones de lo que enviamos
    python ver_logs.py --raw           # ultimos payloads crudos (wsp_raw_inbox)
    python ver_logs.py --raw --errores # solo los raw con estado ERROR
    python ver_logs.py --raw --id 9    # el payload completo de un id_raw
"""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path("/opt/userchuck/config")
load_dotenv(CONFIG_DIR / "database.env")

from webhook.db import obtener_conexion  # noqa: E402 - necesita el .env cargado


def leer(valor):
    """Devuelve el contenido de un CLOB (o el valor tal cual si no lo es)."""
    return valor.read() if hasattr(valor, "read") else valor


def mostrar_mensajes(cursor, cantidad, direccion):
    filtro = "WHERE direccion = :direccion" if direccion else ""
    cursor.execute(
        f"""
        SELECT id_log, fecha_registro, direccion, wa_id, wa_name,
               tipo_mensaje, texto_mensaje, file_id, wsp_msg_id
        FROM wsp_log_mensajes
        {filtro}
        ORDER BY id_log DESC
        FETCH FIRST :cantidad ROWS ONLY
        """,
        **({"direccion": direccion} if direccion else {}),
        cantidad=cantidad,
    )
    filas = cursor.fetchall()

    if not filas:
        print("Sin registros.")
        return

    for fila in reversed(filas):
        (id_log, fecha, dir_, wa_id, wa_name, tipo, texto, file_id, msg_id) = fila
        quien = f"{wa_id or '?'}" + (f" ({wa_name})" if wa_name else "")
        print(f"[{id_log}] {fecha:%d/%m/%Y %H:%M:%S} {dir_ or '?':8s} {quien}")
        print(f"      tipo={tipo}  texto={leer(texto)!r}")
        if file_id:
            print(f"      file_id={file_id}")
        print(f"      msg_id={msg_id}")


def mostrar_raw(cursor, cantidad, solo_errores, id_raw):
    if id_raw is not None:
        cursor.execute(
            """SELECT id_raw, fecha_ingreso, estado_proceso, mensaje_error,
                      ip_origen, load_json
               FROM wsp_raw_inbox WHERE id_raw = :id_raw""",
            id_raw=id_raw,
        )
        fila = cursor.fetchone()
        if fila is None:
            print(f"No existe id_raw={id_raw}")
            return
        print(f"[{fila[0]}] {fila[1]:%d/%m/%Y %H:%M:%S} {fila[2]} ip={fila[4]}")
        if fila[3]:
            print(f"      error: {fila[3]}")
        payload = leer(fila[5])
        try:
            print(json.dumps(json.loads(payload), ensure_ascii=False, indent=2))
        except ValueError:
            print(payload)
        return

    filtro = "WHERE estado_proceso = 'ERROR'" if solo_errores else ""
    cursor.execute(
        f"""
        SELECT id_raw, fecha_ingreso, estado_proceso, mensaje_error, ip_origen
        FROM wsp_raw_inbox
        {filtro}
        ORDER BY id_raw DESC
        FETCH FIRST :cantidad ROWS ONLY
        """,
        cantidad=cantidad,
    )
    filas = cursor.fetchall()

    if not filas:
        print("Sin registros.")
        return

    for id_raw_, fecha, estado, error, ip in reversed(filas):
        print(f"[{id_raw_}] {fecha:%d/%m/%Y %H:%M:%S} {estado or '?':10s} ip={ip}")
        if error:
            print(f"      error: {error}")
    print("\nPara ver un payload completo: python ver_logs.py --raw --id <id_raw>")


def main():
    parser = argparse.ArgumentParser(description="Ver los logs del webhook de WhatsApp.")
    parser.add_argument("-n", type=int, default=20, help="Cantidad de registros (default: 20)")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--entrantes", action="store_true", help="Solo direccion=ENTRANTE")
    grupo.add_argument("--salientes", action="store_true", help="Solo direccion=SALIENTE")
    parser.add_argument("--raw", action="store_true", help="Consultar wsp_raw_inbox")
    parser.add_argument("--errores", action="store_true", help="Con --raw: solo estado ERROR")
    parser.add_argument("--id", type=int, help="Con --raw: payload completo de ese id_raw")
    args = parser.parse_args()

    direccion = "ENTRANTE" if args.entrantes else "SALIENTE" if args.salientes else None

    with obtener_conexion() as conexion:
        with conexion.cursor() as cursor:
            if args.raw:
                mostrar_raw(cursor, args.n, args.errores, args.id)
            else:
                mostrar_mensajes(cursor, args.n, direccion)


if __name__ == "__main__":
    main()
