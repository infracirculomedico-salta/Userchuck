"""
Asistente de envío: hace preguntas y arma el comando de main.py solo.

Pensado para quien no maneja la terminal: no hay que escribir opciones ni
copiar comandos. Elige el CSV y la plantilla de una lista numerada, pide el
valor de cada variable y corre SIEMPRE una simulación primero. Solo si el
usuario escribe "SI" después de ver el resumen se hace el envío real (que
además pide su propia confirmación s/n en main.py).

Uso:
    /opt/userchuck/enviar
"""

import logging
import subprocess
import sys
from pathlib import Path

from contactos import COLUMNAS_ESPERADAS, _detectar_separador, _leer_texto
from main import CONTACTOS_DIR
from plantillas import COLUMNAS_POR_DEFECTO, PLANTILLAS

MAIN = Path(__file__).resolve().parent / "main.py"

# Importar main configura el logging en INFO; acá solo interesan los
# problemas, no el detalle de cómo se leyó el CSV.
logging.getLogger().setLevel(logging.WARNING)


def elegir(titulo, opciones):
    """
    Muestra una lista numerada y devuelve el índice elegido.

    Args:
        titulo: pregunta que se muestra arriba de la lista.
        opciones: textos a mostrar, uno por renglón.

    Returns:
        int: índice (desde 0) de la opción elegida.
    """
    print(f"\n{titulo}")
    for i, opcion in enumerate(opciones, 1):
        print(f"  {i}) {opcion}")
    while True:
        respuesta = input("Número: ").strip()
        if respuesta.isdigit() and 1 <= int(respuesta) <= len(opciones):
            return int(respuesta) - 1
        print(f"  Escribí un número del 1 al {len(opciones)}.")


def pedir_texto(pregunta):
    """Pide un texto no vacío."""
    while True:
        respuesta = input(f"{pregunta}: ").strip()
        if respuesta:
            return respuesta
        print("  No puede quedar vacío.")


def columnas_extra(ruta):
    """
    Devuelve las columnas del CSV que no son las siete fijas (MONTO,
    PERIODO...), que son las que tiene sentido usar como variables.
    """
    contenido, _ = _leer_texto(ruta)
    encabezado = contenido.splitlines()[0]
    columnas = [c.strip() for c in encabezado.split(_detectar_separador(encabezado))]
    return [c for c in columnas if c and c.upper() not in COLUMNAS_ESPERADAS]


def pedir_variable(variable, extras):
    """
    Pregunta de dónde sale una variable y devuelve el argumento para main.py
    ("--col" o "--valor", "variable=...").
    """
    print(f"\n--- Variable «{variable}» ---")
    if extras:
        opciones = ["Escribir un texto (el mismo para todos)"] + [
            f"Tomarlo de la columna {c} (distinto para cada socio)" for c in extras
        ]
        indice = elegir(f"¿De dónde sale «{variable}»?", opciones)
        if indice > 0:
            return "--col", f"{variable}={extras[indice - 1]}"
    return "--valor", f"{variable}={pedir_texto(f'Texto para «{variable}»')}"


def main():
    # Que los textos del asistente salgan en orden con la salida de main.py.
    sys.stdout.reconfigure(line_buffering=True)
    print("=== Asistente de envío de WhatsApp ===")
    print("Primero se hace una SIMULACIÓN: no se manda nada hasta que lo confirmes.")

    archivos = sorted(CONTACTOS_DIR.glob("*.csv"))
    if not archivos:
        print(f"\nNo hay ningún CSV en {CONTACTOS_DIR}. Copiá ahí el archivo y volvé a empezar.")
        sys.exit(1)
    archivo = archivos[elegir("¿Qué archivo de contactos?", [a.name for a in archivos])]

    nombres = sorted(PLANTILLAS)
    nombre_plantilla = nombres[
        elegir(
            "¿Qué mensaje querés mandar?",
            [f"{n} — {PLANTILLAS[n]['descripcion']}" for n in nombres],
        )
    ]

    argumentos = ["--archivo", archivo.name, "--plantilla", nombre_plantilla]
    a_pedir = [
        v for v in PLANTILLAS[nombre_plantilla]["variables"] if v not in COLUMNAS_POR_DEFECTO
    ]
    if a_pedir:
        extras = columnas_extra(archivo)
        for variable in a_pedir:
            argumentos += pedir_variable(variable, extras)

    print("\n=== SIMULACIÓN (no se envía nada) ===\n")
    simulacion = subprocess.run([sys.executable, str(MAIN), *argumentos, "--simular"])
    if simulacion.returncode != 0:
        print("\nLa simulación dio error (ver arriba). No se envió nada.")
        sys.exit(1)

    print("\nRevisá el resumen de arriba: a cuántos se manda y cómo queda el mensaje.")
    respuesta = input("Para ENVIAR DE VERDAD escribí SI (cualquier otra cosa cancela): ")
    if respuesta.strip().upper() != "SI":
        print("Cancelado. No se envió nada.")
        return

    print("\n=== ENVÍO REAL ===\n")
    envio = subprocess.run([sys.executable, str(MAIN), *argumentos])
    sys.exit(envio.returncode)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        sys.exit(1)
