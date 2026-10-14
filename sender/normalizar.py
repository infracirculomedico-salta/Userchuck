"""
Normalización de números de teléfono argentinos al formato E.164
esperado por la WhatsApp Cloud API.

Los números vienen de un formulario completado a mano, así que llegan en
todas las formas en que un argentino escribe su celular: con el 0 de
larga distancia, con el 15 de celular, ya en E.164, con espacios y
guiones. Todas se reducen acá al mismo formato "+549" + los 10 dígitos
del número nacional.

El número nacional argentino (código de área + abonado) tiene siempre 10
dígitos, y el 15 son dos dígitos extra que se intercalan después del
código de área: un número con 15 tiene 12 dígitos.
"""

import re

CARACTERES_A_LIMPIAR = re.compile(r"[\s\-\(\)\.]")

# Largo del número nacional argentino (código de área + abonado).
LARGO_NACIONAL = 10

# Posiciones posibles del "15" dentro de un número de 12 dígitos, una por
# cada largo de código de área que se usa en el país (2, 3 y 4 dígitos).
POSICIONES_DEL_15 = (2, 3, 4)

# Todos los códigos de área del país empiezan con "11" (CABA), "2" o "3".
# Sirve para descartar un número al que le sobra o le falta un prefijo:
# "1538741234" son diez dígitos, pero no existe el área "15", así que es
# un celular al que le sacaron el código de área, no un número válido.
PREFIJOS_DE_AREA = ("11", "2", "3")

MOTIVO_OK = ""


def _quitar_prefijo_internacional(digitos):
    """
    Saca el 54 de país y el 9 de celular, si están.

    El 9 solo se saca cuando venía precedido del 54: un número nacional
    puede empezar con 9 por sí mismo (el área 9xxx no existe hoy, pero la
    regla se mantiene acotada a lo que se sabe cierto).
    """
    if digitos.startswith("54"):
        digitos = digitos[2:]
        if digitos.startswith("9"):
            digitos = digitos[1:]
    return digitos


def _quitar_15(digitos):
    """
    Saca el 15 de un número de 12 dígitos.

    Busca el "15" en las tres posiciones donde puede estar según el largo
    del código de área. Si más de una posición da un resultado distinto y
    plausible, el número es ambiguo y se rechaza en lugar de adivinar.

    Returns:
        tuple[str | None, str]: (digitos_sin_15, motivo). Si no se pudo
        resolver, el primer elemento es None y motivo explica por qué.
    """
    candidatos = set()

    for posicion in POSICIONES_DEL_15:
        if digitos[posicion:posicion + 2] != "15":
            continue
        sin_15 = digitos[:posicion] + digitos[posicion + 2:]
        if sin_15.startswith(PREFIJOS_DE_AREA):
            candidatos.add(sin_15)

    if not candidatos:
        return None, "12 dígitos y no se encontró el 15 después del código de área"

    if len(candidatos) > 1:
        return None, "ambiguo: el 15 puede estar en más de una posición"

    return candidatos.pop(), MOTIVO_OK


def normalizar_numero_con_motivo(numero):
    """
    Normaliza un número argentino al formato E.164 de WhatsApp.

    Acepta, entre otras formas: "3874488152", "0387 4488152",
    "0387 15 4488152", "387154488152", "+5493874488152",
    "5493874488152", con espacios, guiones, puntos o paréntesis.

    Args:
        numero: número de teléfono tal como vino del formulario.

    Returns:
        tuple[str | None, str]: (numero_normalizado, motivo).
        Si se pudo normalizar, motivo es "". Si no, el número es None y
        motivo dice qué pasó, para poder registrarlo en el log de envío
        en vez de descartar al contacto en silencio.
    """
    if numero is None:
        return None, "vacío"

    digitos = CARACTERES_A_LIMPIAR.sub("", str(numero).strip())

    if not digitos:
        return None, "vacío"

    if digitos.startswith("+"):
        digitos = digitos[1:]

    if not digitos.isdigit():
        return None, "tiene caracteres que no son dígitos"

    digitos = _quitar_prefijo_internacional(digitos)

    # El 0 de larga distancia va después del 54: "0387..." y "540387..."
    # son la misma forma escrita distinto.
    if digitos.startswith("0"):
        digitos = digitos[1:]

    if len(digitos) == LARGO_NACIONAL + 2:
        digitos, motivo = _quitar_15(digitos)
        if digitos is None:
            return None, motivo

    if len(digitos) != LARGO_NACIONAL:
        return None, f"quedaron {len(digitos)} dígitos, se esperaban {LARGO_NACIONAL}"

    if not digitos.startswith(PREFIJOS_DE_AREA):
        return None, f"no empieza con un código de área válido ({digitos[:3]}...)"

    return f"+549{digitos}", MOTIVO_OK


def normalizar_numero(numero):
    """
    Versión corta de normalizar_numero_con_motivo, para quien no necesita
    saber por qué falló.

    Returns:
        str | None: número en formato E.164, o None si no se pudo
        normalizar.
    """
    normalizado, _ = normalizar_numero_con_motivo(numero)
    return normalizado
