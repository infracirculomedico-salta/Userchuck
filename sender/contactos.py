"""
Lectura y validación del CSV de contactos para el envío masivo de WhatsApp.
"""

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

COLUMNAS_ESPERADAS = [
    "FECHA",
    "MAIL",
    "APEYNOM",
    "DNI",
    "MATRICULA",
    "WHATSAPP",
    "ESTADO_CONSENTIMIENTO",
]

# Encodings a probar, en orden. UTF-8 va primero a propósito: es estricto
# y falla ruidosamente si el archivo no lo es, mientras que latin-1 mapea
# cualquier byte a algún carácter y nunca falla. Si se probara latin-1
# primero, un CSV en UTF-8 se leería entero como mojibake sin una sola
# advertencia ("José" -> "JosÃ©") y ese nombre saldría en el mensaje.
# "utf-8-sig" además saca el BOM que agrega Excel al exportar.
ENCODINGS = ("utf-8-sig", "latin-1")

# Separadores posibles del CSV, en orden de preferencia. El archivo que
# exporta el CMS usa ";", pero pasar por Excel o Google Sheets lo puede
# convertir a tabulaciones o comas, y el separador equivocado hace que
# csv lea toda la línea como una sola columna: el error que sale es
# "faltan columnas", que no dice nada sobre la causa real.
SEPARADORES = (";", "\t", ",")

# Secuencias que aparecen cuando un archivo UTF-8 se lee como latin-1.
# Si están, la lectura "funcionó" pero el contenido está corrupto.
MOJIBAKE = re.compile(r"[ÃÂ][\x80-\xbf©±¡¿³-]")


def _leer_texto(ruta):
    """
    Lee el archivo probando los encodings de ENCODINGS en orden.

    Returns:
        tuple[str, str]: (contenido, encoding_usado).

    Raises:
        UnicodeDecodeError: si ninguno de los encodings sirvió.
    """
    ultimo_error = None

    for encoding in ENCODINGS:
        try:
            contenido = ruta.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            logger.info("El CSV no es %s (%s), se prueba el siguiente.", encoding, error.reason)
            ultimo_error = error
            continue

        logger.info("CSV leído como %s", encoding)
        return contenido, encoding

    raise ultimo_error


def _advertir_si_hay_mojibake(contenido, encoding):
    """
    Avisa si el texto quedó con los acentos corruptos.

    Solo puede pasar con latin-1, que acepta cualquier byte: si el
    archivo era UTF-8 y se leyó así, los acentos ya están arruinados y
    van a salir en el mensaje que recibe el socio.
    """
    if encoding == "utf-8-sig":
        return

    muestra = MOJIBAKE.findall(contenido)
    if muestra:
        logger.warning(
            "El CSV se leyó como %s pero tiene %d secuencias que parecen UTF-8 mal "
            "decodificado (ej: %s). Los acentos van a salir corruptos en el mensaje. "
            "Pedí el archivo con el encoding confirmado antes de enviar.",
            encoding,
            len(muestra),
            ", ".join(sorted(set(muestra))[:5]),
        )


def _detectar_separador(encabezado):
    """
    Elige el separador con el que el encabezado da más columnas conocidas.

    Args:
        encabezado: primera línea del archivo.

    Returns:
        str: el separador elegido.

    Raises:
        ValueError: si con ninguno aparecen las columnas esperadas.
    """
    mejor = None
    mejor_puntaje = 0

    for separador in SEPARADORES:
        columnas = {c.strip().upper() for c in encabezado.split(separador)}
        puntaje = len(columnas & set(COLUMNAS_ESPERADAS))
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = separador, puntaje

    if mejor is None:
        raise ValueError(
            "No se reconoció el separador del CSV: con ';', tabulación ni ',' "
            f"aparecen las columnas esperadas. Primera línea: {encabezado[:120]!r}"
        )

    logger.info("Separador detectado: %r (%d columnas conocidas)", mejor, mejor_puntaje)
    return mejor


def leer_contactos(ruta_csv):
    """
    Lee el CSV de contactos (separador ";") y devuelve solo las filas
    donde ESTADO_CONSENTIMIENTO == "ACEPTO" (case insensitive).

    El encoding se detecta probando UTF-8 y cayendo a latin-1, y se
    registra cuál se usó: leerlo con el encoding equivocado no da error,
    corrompe los acentos en silencio.

    Args:
        ruta_csv: ruta al archivo CSV.

    Returns:
        tuple[list[dict], int]: (contactos_validos, cantidad_excluidos)
        donde contactos_validos son las filas con consentimiento y
        cantidad_excluidos es la cantidad de filas descartadas por no
        tener ESTADO_CONSENTIMIENTO == "ACEPTO".

    Raises:
        ValueError: si al CSV le faltan columnas esperadas.
        UnicodeDecodeError: si no se pudo leer con ningún encoding.
    """
    ruta = Path(ruta_csv)

    contenido, encoding = _leer_texto(ruta)
    _advertir_si_hay_mojibake(contenido, encoding)

    lineas = contenido.splitlines()
    if not lineas:
        raise ValueError(f"El CSV {ruta} está vacío")

    lector = csv.DictReader(lineas, delimiter=_detectar_separador(lineas[0]))

    faltantes = [c for c in COLUMNAS_ESPERADAS if c not in (lector.fieldnames or [])]
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas en el CSV: {faltantes}")

    contactos_validos = []
    excluidos = 0

    for fila in lector:
        estado = (fila.get("ESTADO_CONSENTIMIENTO") or "").strip().upper()
        if estado == "ACEPTO":
            contactos_validos.append(fila)
        else:
            excluidos += 1

    logger.info("Contactos válidos (ACEPTO): %d", len(contactos_validos))
    logger.info("Contactos excluidos (sin ACEPTO): %d", excluidos)

    return contactos_validos, excluidos
