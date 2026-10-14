"""
Orquestador de envío masivo de plantillas de WhatsApp Business API.

Lee un CSV de contactos, filtra por consentimiento (ESTADO_CONSENTIMIENTO
== "ACEPTO"), normaliza los números al formato E.164, y envía la plantilla
indicada a cada contacto válido vía la WhatsApp Cloud API.

Las plantillas disponibles están declaradas en plantillas.py, con su
idioma, su formato de parámetros y los nombres de sus variables tal como
los registró Meta. El sender no acepta plantillas que no estén ahí:
así se evita descubrir en pleno envío que el nombre, el idioma o el
formato de parámetros no coincidían.

Cada variable de la plantilla necesita un origen:

    --col variable=COLUMNA    toma el valor de esa columna del CSV
                              (distinto por contacto)
    --valor variable=texto    usa el mismo texto para todo el envío

La variable "nombre" sale por defecto de la columna APEYNOM, así que
normalmente no hace falta mapearla.

Uso:
    python main.py --listar

    python main.py --archivo contactos.csv \
        --plantilla notificacion_liquidacion \
        --col monto=MONTO --valor periodo="agosto 2026" --simular

    python main.py --archivo contactos.csv \
        --plantilla aviso_suspension_prestacion --modo cron

Modo "manual" (default): muestra un resumen y pide confirmación (s/n)
antes de enviar.
Modo "cron": no pide ninguna confirmación interactiva, pensado para
correr desde crontab sin intervención humana. Ante cualquier duda
(plantilla no aprobada, columna faltante) aborta en lugar de preguntar.

--simular arma y valida todo sin llamar a la API de envío: no consume
mensajes ni llega nada a los destinatarios.
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from contactos import leer_contactos
from normalizar import normalizar_numero_con_motivo
from plantillas import (
    PLANTILLAS,
    obtener_plantilla,
    parsear_asignacion,
    resolver_origenes,
)
from whatsapp_api import consultar_plantilla, enviar_plantilla, limpiar_parametro

SENDER_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path("/opt/userchuck/sender/config")
LOGS_DIR = SENDER_DIR / "logs"
CONTACTOS_DIR = Path("/opt/userchuck/contactos")

# Estado que Meta le pone a una plantilla lista para usar. Cualquier otro
# (PENDING, REJECTED, PAUSED, DISABLED) hace que el envío falle mensaje
# por mensaje.
ESTADO_APROBADO = "APPROVED"

# Espera entre mensajes. La Cloud API tolera bastante más que esto, pero
# a 0.2s los 431 socios salen en un minuto y medio y no se llega nunca al
# 429, que obliga a esperar mucho más de lo que se ahorró.
PAUSA_POR_DEFECTO = 0.2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Envío masivo de plantillas de WhatsApp Business API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplo:\n"
            "  python main.py --archivo contactos.csv "
            "--plantilla solicitud_documentacion \\\n"
            '      --valor tramite="reempadronamiento" '
            '--valor documentacion="DNI y matrícula" --simular'
        ),
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Muestra las plantillas registradas con sus variables y termina.",
    )
    parser.add_argument(
        "--archivo",
        help=(
            f"Nombre del CSV de contactos dentro de {CONTACTOS_DIR} "
            "(con o sin .csv). También acepta una ruta completa."
        ),
    )
    parser.add_argument(
        "--plantilla", help="Nombre de la plantilla (tiene que estar en plantillas.py)"
    )
    parser.add_argument(
        "--col",
        action="append",
        default=[],
        metavar="VARIABLE=COLUMNA",
        help=(
            "Toma el valor de la variable de esa columna del CSV, distinto por "
            'contacto (ej: --col monto=MONTO). Se puede repetir.'
        ),
    )
    parser.add_argument(
        "--valor",
        action="append",
        default=[],
        metavar="VARIABLE=TEXTO",
        help=(
            "Usa el mismo texto para esa variable en todo el envío "
            '(ej: --valor periodo="agosto 2026"). Se puede repetir.'
        ),
    )
    parser.add_argument(
        "--modo",
        choices=["manual", "cron"],
        default="manual",
        help="manual: pide confirmación antes de enviar. cron: no pide confirmación.",
    )
    parser.add_argument(
        "--idioma",
        default=None,
        help=(
            "Fuerza el código de idioma de la plantilla. Por defecto se usa el "
            "que declara plantillas.py (es_AR en todas)."
        ),
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Valida y arma todos los mensajes sin enviarlos (no consume mensajes).",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA_POR_DEFECTO,
        help=(
            "Segundos de espera entre mensajes, para no pegarle al límite de tasa "
            f"de Meta. Default: {PAUSA_POR_DEFECTO}."
        ),
    )
    parser.add_argument(
        "--reanudar",
        metavar="LOG_CSV",
        help=(
            "Ruta a un CSV de log de un envío anterior: los contactos que ya "
            "figuran con resultado OK se omiten. Sirve para retomar un envío "
            "que se cortó sin mandarle dos veces a nadie."
        ),
    )
    parser.add_argument(
        "--sin-verificar",
        action="store_true",
        help="No consulta a Meta el estado de la plantilla antes de enviar.",
    )
    return parser.parse_args()


def listar_plantillas():
    """Imprime el registro de plantillas con sus variables y formato."""
    print("=== Plantillas registradas ===")
    for nombre in sorted(PLANTILLAS):
        plantilla = PLANTILLAS[nombre]
        variables = ", ".join(plantilla["variables"]) or "(sin variables)"
        print(f"\n{nombre}")
        print(f"  {plantilla['descripcion']}")
        print(f"  idioma: {plantilla['idioma']}   categoría: {plantilla['categoria']}")
        print(f"  formato: {plantilla['formato']}")
        print(f"  variables: {variables}")


def verificar_plantilla_en_meta(plantilla, nombre_plantilla, access_token):
    """
    Consulta el estado de la plantilla en Meta y avisa si algo no cierra.

    Compara además nombre, idioma y formato de parámetros contra lo que
    declara plantillas.py: si el registro quedó desactualizado respecto
    de Meta, es preferible enterarse ahora y no mensaje por mensaje.

    Returns:
        tuple[bool, list[str]]: (todo_ok, advertencias). todo_ok es False
        si la plantilla existe pero no está aprobada, o si hay una
        diferencia con el registro. Si la consulta no se pudo hacer,
        devuelve True con una advertencia: un problema de red no debería
        bloquear un envío por sí solo.
    """
    datos, detalle = consultar_plantilla(plantilla["id_meta"], access_token)

    if datos is None:
        return True, [f"No se pudo verificar la plantilla en Meta ({detalle})."]

    advertencias = []
    todo_ok = True

    estado = datos.get("status")
    if estado != ESTADO_APROBADO:
        todo_ok = False
        advertencias.append(
            f"La plantilla está en estado {estado} en Meta, no {ESTADO_APROBADO}. "
            "Los envíos van a fallar hasta que Meta la apruebe."
        )

    for clave_registro, clave_meta, etiqueta in (
        ("idioma", "language", "idioma"),
        ("formato", "parameter_format", "formato de parámetros"),
    ):
        if datos.get(clave_meta) != plantilla[clave_registro]:
            todo_ok = False
            advertencias.append(
                f"El {etiqueta} no coincide: plantillas.py dice "
                f"{plantilla[clave_registro]!r} y Meta dice {datos.get(clave_meta)!r}. "
                "Hay que actualizar plantillas.py."
            )

    if datos.get("name") != nombre_plantilla:
        todo_ok = False
        advertencias.append(
            f"El id {plantilla['id_meta']} corresponde a la plantilla "
            f"{datos.get('name')!r}, no a {nombre_plantilla!r}."
        )

    return todo_ok, advertencias


def validar_columnas(origenes, fila_ejemplo):
    """
    Devuelve las columnas mapeadas con --col que no existen en el CSV.

    Se controla contra una fila real y no contra COLUMNAS_ESPERADAS
    porque el CSV puede traer columnas extra (MONTO, PERIODO...) que son
    justamente las que se mapean a variables.
    """
    return sorted(
        columna
        for origen, columna in origenes.values()
        if origen == "columna" and columna not in fila_ejemplo
    )


def construir_valores(fila, origenes):
    """
    Arma los valores de las variables de la plantilla para un contacto.

    Args:
        fila: dict de la fila del CSV.
        origenes: dict variable -> ("columna", COLUMNA) | ("fijo", texto).

    Returns:
        tuple[dict, list[str]]: (valores, variables_vacias).
        valores mapea cada variable a su texto ya limpio para Meta, y
        variables_vacias lista las que quedaron sin contenido (Meta
        rechaza los parámetros vacíos, así que ese contacto no se envía).
    """
    valores = {}
    vacias = []

    for variable, (origen, referencia) in origenes.items():
        crudo = fila.get(referencia, "") if origen == "columna" else referencia
        valor = limpiar_parametro(crudo)
        if not valor:
            vacias.append(variable)
        valores[variable] = valor

    return valores, vacias


def preparar_parametros(valores, plantilla):
    """
    Adapta los valores al formato de parámetros que espera la plantilla.

    Las plantillas NAMED viajan como dict {variable: valor}; las
    POSITIONAL, como lista en el orden declarado por el registro.
    """
    if plantilla["formato"] == "NAMED":
        return {variable: valores[variable] for variable in plantilla["variables"]}
    return [valores[variable] for variable in plantilla["variables"]]


def leer_enviados(ruta_log, nombre_plantilla):
    """
    Lee un CSV de log anterior y devuelve a quiénes ya les llegó el mensaje.

    Args:
        ruta_log: ruta al CSV de log del envío que se quiere retomar.
        nombre_plantilla: plantilla del envío actual, para verificar que
            el log sea del mismo envío.

    Returns:
        set[str]: números normalizados con resultado OK.

    Raises:
        ValueError: si el log es de otra plantilla. Retomar con el log
            equivocado saltearía contactos que nunca recibieron nada.
    """
    ruta = Path(ruta_log)
    enviados = set()
    plantillas = set()

    with ruta.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            plantillas.add(fila.get("plantilla", ""))
            if fila.get("resultado") == "OK" and fila.get("numero_normalizado"):
                enviados.add(fila["numero_normalizado"])

    ajenas = plantillas - {nombre_plantilla}
    if ajenas:
        raise ValueError(
            f"El log {ruta} es de la plantilla {', '.join(sorted(ajenas))}, no de "
            f"{nombre_plantilla}. Retomar con ese log saltearía contactos que nunca "
            "recibieron el mensaje."
        )

    logger.info("Reanudando: %d contactos ya recibieron %s", len(enviados), nombre_plantilla)
    return enviados


def abrir_log(nombre_plantilla):
    """
    Abre el CSV de log del envío y escribe el encabezado.

    El log se va escribiendo mensaje por mensaje, no al final: si el
    proceso se corta a mitad de un envío de cientos de contactos, lo ya
    enviado tiene que quedar registrado para poder retomarlo con
    --reanudar sin mandarle dos veces a nadie.

    Returns:
        tuple: (archivo, escritor_csv, ruta). El archivo queda abierto;
        cerrarlo es responsabilidad de quien llama.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # El nombre lleva la hora al segundo, así que dos envíos seguidos
    # pueden caer en el mismo archivo. Eso importa al reanudar: el log
    # nuevo pisaría el que se está usando como fuente de lo ya enviado.
    ruta_log = LOGS_DIR / f"envio_{timestamp}.csv"
    repeticion = 2
    while ruta_log.exists():
        ruta_log = LOGS_DIR / f"envio_{timestamp}_{repeticion}.csv"
        repeticion += 1

    archivo = ruta_log.open("w", newline="", encoding="utf-8")
    escritor = csv.writer(archivo)
    escritor.writerow(
        [
            "plantilla",
            "nombre",
            "numero_original",
            "numero_normalizado",
            "resultado",
            "detalle",
        ]
    )
    archivo.flush()

    logger.info("Log de envío: %s", ruta_log)
    return archivo, escritor, ruta_log


def resolver_archivo(nombre):
    """
    Encuentra el CSV de contactos a partir de lo que se pasó en --archivo.

    Lo normal es pasar solo el nombre ("liquidaciones_agosto" o
    "liquidaciones_agosto.csv") y que se busque en CONTACTOS_DIR. Una ruta
    que ya existe tal cual se usa sin tocar, para no romper los comandos
    que pasan la ruta completa.

    Returns:
        Path: ruta al CSV.

    Raises:
        FileNotFoundError: si no está, con la lista de los CSV disponibles.
    """
    ruta = Path(nombre)
    if ruta.is_file():
        return ruta

    candidatos = [CONTACTOS_DIR / ruta.name]
    if ruta.suffix.lower() != ".csv":
        candidatos.append(CONTACTOS_DIR / f"{ruta.name}.csv")
    for candidato in candidatos:
        if candidato.is_file():
            return candidato

    disponibles = sorted(p.name for p in CONTACTOS_DIR.glob("*.csv"))
    lista = "\n".join(f"    {d}" for d in disponibles) or "    (no hay ninguno)"
    raise FileNotFoundError(
        f"No se encontró '{nombre}' en {CONTACTOS_DIR}. Los CSV que hay son:\n{lista}"
    )


def confirmar(pregunta):
    """Pide una confirmación por consola. Devuelve True solo ante "s"."""
    return input(f"{pregunta} (s/n): ").strip().lower() == "s"


def abortar_o_preguntar(modo, mensaje, pregunta):
    """
    Resuelve una situación dudosa según el modo de ejecución.

    En modo cron aborta (no hay nadie para contestar); en modo manual
    pregunta si se sigue igual. Si no se sigue, termina el proceso.
    """
    if modo == "cron":
        logger.error("%s Modo cron: se aborta automáticamente.", mensaje)
        sys.exit(1)

    print(mensaje)
    if not confirmar(pregunta):
        logger.info("Envío cancelado por el usuario.")
        sys.exit(0)


def main():
    args = parsear_argumentos()

    if args.listar:
        listar_plantillas()
        return

    if not args.archivo or not args.plantilla:
        logger.error("Faltan --archivo y/o --plantilla (o usá --listar).")
        sys.exit(1)

    try:
        archivo = resolver_archivo(args.archivo)
    except FileNotFoundError as error:
        logger.error("%s", error)
        sys.exit(1)

    load_dotenv(CONFIG_DIR / "whatsapp.env")
    access_token = os.environ.get("META_ACCESS_TOKEN")
    phone_number_id = os.environ.get("META_PHONE_NUMBER_ID")

    if not access_token or not phone_number_id:
        logger.error(
            "Faltan META_ACCESS_TOKEN y/o META_PHONE_NUMBER_ID en %s",
            CONFIG_DIR / "whatsapp.env",
        )
        sys.exit(1)

    # Plantilla y orígenes de sus variables: todo esto se valida antes de
    # tocar el CSV y mucho antes de enviar nada.
    try:
        plantilla = obtener_plantilla(args.plantilla)
        columnas = dict(parsear_asignacion(a, "--col") for a in args.col)
        valores_fijos = dict(parsear_asignacion(a, "--valor") for a in args.valor)
        origenes = resolver_origenes(plantilla, columnas, valores_fijos)
    except ValueError as error:
        logger.error("%s", error)
        sys.exit(1)

    idioma = args.idioma or plantilla["idioma"]

    if not args.sin_verificar:
        todo_ok, advertencias = verificar_plantilla_en_meta(
            plantilla, args.plantilla, access_token
        )
        for advertencia in advertencias:
            logger.warning("%s", advertencia)
        if not todo_ok and not args.simular:
            abortar_o_preguntar(
                args.modo,
                "La plantilla no está en condiciones de usarse (ver advertencias).",
                "¿Intentar el envío igual?",
            )

    ya_enviados = set()
    if args.reanudar:
        try:
            ya_enviados = leer_enviados(args.reanudar, args.plantilla)
        except (OSError, ValueError) as error:
            logger.error("%s", error)
            sys.exit(1)

    contactos_validos, excluidos_consentimiento = leer_contactos(archivo)

    if contactos_validos:
        faltantes = validar_columnas(origenes, contactos_validos[0])
        if faltantes:
            logger.error(
                "Estas columnas mapeadas con --col no existen en el CSV: %s",
                ", ".join(faltantes),
            )
            sys.exit(1)

    # Normaliza el número y arma los valores de plantilla de cada contacto
    # ya filtrado por consentimiento.
    contactos_preparados = []
    numeros_invalidos = []
    con_variables_vacias = 0

    for fila in contactos_validos:
        numero_original = fila.get("WHATSAPP", "")
        numero_normalizado, motivo = normalizar_numero_con_motivo(numero_original)
        valores, vacias = construir_valores(fila, origenes)

        if numero_normalizado is None:
            numeros_invalidos.append((numero_original, motivo))
        elif vacias:
            con_variables_vacias += 1

        contactos_preparados.append(
            (fila, numero_original, numero_normalizado, valores, motivo, vacias)
        )

    cantidad_para_envio = sum(
        1
        for _, _, numero, _, _, vacias in contactos_preparados
        if numero and not vacias and numero not in ya_enviados
    )

    # Un número que no se puede normalizar es un socio que dio su
    # consentimiento y no va a recibir nada: tiene que verse siempre, no
    # solo al abrir el CSV de log después del envío.
    for numero_original, motivo in numeros_invalidos:
        logger.warning("Número descartado: %r (%s)", numero_original, motivo)

    if args.modo == "manual" or args.simular:
        print("=== Resumen de envío ===")
        print(f"Plantilla: {args.plantilla} ({plantilla['categoria']}, {idioma})")
        print(f"Formato de parámetros: {plantilla['formato']}")
        for variable, (origen, referencia) in origenes.items():
            detalle = f"columna {referencia}" if origen == "columna" else f"fijo {referencia!r}"
            print(f"  {variable}: {detalle}")
        print(f"Contactos con consentimiento (ACEPTO): {len(contactos_validos)}")
        print(f"Excluidos por NO ACEPTO: {excluidos_consentimiento}")
        print(f"Números inválidos: {len(numeros_invalidos)}")
        print(f"Con variables vacías (no se envían): {con_variables_vacias}")
        if ya_enviados:
            print(f"Omitidos por --reanudar (ya recibieron): {len(ya_enviados)}")
        print(f"Pausa entre mensajes: {args.pausa}s")
        print(f"Se van a enviar: {cantidad_para_envio}")

        if contactos_preparados:
            _, _, numero_muestra, valores_muestra, _, _ = contactos_preparados[0]
            print(f"Primer mensaje: {numero_muestra} -> {valores_muestra}")

    if args.simular:
        logger.info("Modo simulación: no se envió ningún mensaje.")
        return

    if args.modo == "manual" and not confirmar("¿Confirmás el envío?"):
        logger.info("Envío cancelado por el usuario.")
        sys.exit(0)

    archivo_log, escritor_log, ruta_log = abrir_log(args.plantilla)
    enviados = 0
    fallidos = 0
    omitidos = 0

    def registrar(fila_log):
        """Escribe una fila en el log y la baja a disco en el momento."""
        escritor_log.writerow([args.plantilla] + fila_log)
        archivo_log.flush()

    try:
        for fila, numero_original, numero_normalizado, valores, motivo, vacias in contactos_preparados:
            nombre = fila.get("APEYNOM", "")

            if numero_normalizado is None:
                registrar([nombre, numero_original, "", "ERROR", f"Número inválido: {motivo}"])
                fallidos += 1
                continue

            if vacias:
                detalle = f"Variables sin valor: {', '.join(vacias)}"
                logger.warning("%s, se omite %s", detalle, numero_normalizado)
                registrar([nombre, numero_original, numero_normalizado, "ERROR", detalle])
                fallidos += 1
                continue

            if numero_normalizado in ya_enviados:
                registrar([nombre, numero_original, numero_normalizado, "OMITIDO", "Ya enviado"])
                omitidos += 1
                continue

            # La pausa va antes de cada mensaje menos del primero: separa
            # los pedidos entre sí sin agregar espera al arranque.
            if enviados or fallidos:
                time.sleep(args.pausa)

            exito, detalle = enviar_plantilla(
                numero_destino=numero_normalizado,
                nombre_plantilla=args.plantilla,
                parametros=preparar_parametros(valores, plantilla),
                access_token=access_token,
                phone_number_id=phone_number_id,
                idioma=idioma,
            )
            resultado = "OK" if exito else "ERROR"
            registrar([nombre, numero_original, numero_normalizado, resultado, detalle])
            enviados += exito
            fallidos += not exito
            logger.info("%s -> %s: %s", numero_normalizado, resultado, detalle)

    except KeyboardInterrupt:
        # El log ya tiene en disco todo lo enviado hasta acá, así que se
        # puede retomar sin mandarle dos veces a nadie.
        logger.warning(
            "Envío interrumpido. Para retomarlo:\n"
            "    --reanudar %s",
            ruta_log,
        )
    finally:
        archivo_log.close()

    logger.info(
        "Envío finalizado: %d OK / %d con error / %d omitidos por reanudación",
        enviados,
        fallidos,
        omitidos,
    )
    if fallidos:
        logger.info("Para reintentar solo los que fallaron: --reanudar %s", ruta_log)

if __name__ == "__main__":
    main()
