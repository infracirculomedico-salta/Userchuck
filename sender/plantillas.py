"""
Registro de las plantillas de WhatsApp del Círculo Médico de Salta
aprobadas en Meta Business Manager.

Los datos de cada plantilla (id, idioma, categoría, formato de
parámetros y nombres de las variables) están tomados de la propia API de
Meta (GET /<id-de-plantilla>), no del texto que se cargó en el
formulario: son los que la API espera al momento de enviar.

Si se crea, se edita o se da de baja una plantilla en Meta, hay que
actualizar este archivo. `python main.py --listar` muestra el registro
tal como lo ve el sender.

Sobre el formato de parámetros
------------------------------
Meta distingue dos formatos, y el payload de envío cambia según cuál
sea:

- NAMED: la plantilla se escribió con variables nombradas ({{nombre}},
  {{periodo}}...). Cada parámetro viaja con su "parameter_name" y el
  orden no importa.
- POSITIONAL: variables numeradas ({{1}}, {{2}}...). Los parámetros
  viajan sin nombre y el orden es lo único que los identifica.

Una plantilla NAMED enviada como posicional (o al revés) es rechazada
por Meta con error 132000 / 132012.
"""

# Variables de plantilla que, si no se indica otra cosa, se toman de una
# columna del CSV de contactos. El resto hay que mapearlas a mano con
# --col o --valor.
COLUMNAS_POR_DEFECTO = {
    "nombre": "APEYNOM",
}

PLANTILLAS = {
    "notificacion_liquidacion": {
        "id_meta": "2131542081114268",
        "idioma": "es_AR",
        "categoria": "UTILITY",
        "formato": "NAMED",
        "variables": ["nombre", "periodo", "monto"],
        "descripcion": "Avisa que la liquidación de un período está disponible.",
    },
    "confirmacion_recepcion_solicitud": {
        "id_meta": "1104429218605016",
        "idioma": "es_AR",
        "categoria": "UTILITY",
        "formato": "NAMED",
        "variables": ["nombre", "tramite"],
        "descripcion": "Confirma que se recibió una solicitud y que está en gestión.",
    },
    "solicitud_documentacion": {
        "id_meta": "2072063770108354",
        "idioma": "es_AR",
        "categoria": "UTILITY",
        "formato": "NAMED",
        "variables": ["nombre", "tramite", "documentacion"],
        "descripcion": "Pide la documentación que falta para continuar un trámite.",
    },
    "aviso_suspension_prestacion": {
        "id_meta": "1614721747016577",
        "idioma": "es_AR",
        "categoria": "MARKETING",
        "formato": "NAMED",
        "variables": ["nombre"],
        "descripcion": "Informa que una prestación tiene disponibilidad limitada.",
    },
    "bienvenida_menu_principal": {
        "id_meta": "3980444668918475",
        "idioma": "es_AR",
        "categoria": "MARKETING",
        "formato": "POSITIONAL",
        "variables": [],
        "descripcion": "Presenta el canal institucional. No lleva variables.",
    },
    "aviso_institucional_general": {
        "id_meta": "1793083088432610",
        "idioma": "es_AR",
        "categoria": "MARKETING",
        "formato": "NAMED",
        "variables": ["nombre", "detalle_aviso"],
        "descripcion": "Aviso institucional genérico, con el texto en detalle_aviso.",
    },
}


def obtener_plantilla(nombre):
    """
    Devuelve el dict de configuración de una plantilla del registro.

    Args:
        nombre: nombre de la plantilla tal como figura en Meta.

    Returns:
        dict con id_meta, idioma, categoria, formato, variables y
        descripcion.

    Raises:
        ValueError: si la plantilla no está en el registro, listando las
        disponibles.
    """
    if nombre not in PLANTILLAS:
        disponibles = ", ".join(sorted(PLANTILLAS))
        raise ValueError(
            f"La plantilla '{nombre}' no está en el registro de plantillas.py. "
            f"Disponibles: {disponibles}"
        )
    return PLANTILLAS[nombre]


def resolver_origenes(plantilla, columnas, valores_fijos):
    """
    Decide, para cada variable de la plantilla, de dónde sale su valor.

    Cada variable puede venir de una columna del CSV (distinto valor por
    contacto) o de un valor fijo para todo el envío (por ejemplo el
    período de una liquidación).

    Args:
        plantilla: dict devuelto por obtener_plantilla.
        columnas: dict variable -> nombre de columna del CSV (--col).
        valores_fijos: dict variable -> texto literal (--valor).

    Returns:
        dict variable -> ("columna", nombre_columna) | ("fijo", texto),
        con las variables en el orden en que las declara la plantilla.

    Raises:
        ValueError: si una variable quedó sin origen, si se le dieron
        dos orígenes a la vez, o si se mapeó una variable que la
        plantilla no tiene.
    """
    variables = plantilla["variables"]

    desconocidas = sorted(
        (set(columnas) | set(valores_fijos)) - set(variables)
    )
    if desconocidas:
        esperadas = ", ".join(variables) if variables else "(ninguna)"
        raise ValueError(
            f"Estas variables no existen en la plantilla: {', '.join(desconocidas)}. "
            f"Variables de la plantilla: {esperadas}"
        )

    ambiguas = sorted(set(columnas) & set(valores_fijos))
    if ambiguas:
        raise ValueError(
            "Estas variables tienen --col y --valor a la vez, hay que elegir uno: "
            f"{', '.join(ambiguas)}"
        )

    origenes = {}
    sin_origen = []

    for variable in variables:
        if variable in columnas:
            origenes[variable] = ("columna", columnas[variable])
        elif variable in valores_fijos:
            origenes[variable] = ("fijo", valores_fijos[variable])
        elif variable in COLUMNAS_POR_DEFECTO:
            origenes[variable] = ("columna", COLUMNAS_POR_DEFECTO[variable])
        else:
            sin_origen.append(variable)

    if sin_origen:
        raise ValueError(
            "Faltan orígenes para estas variables: "
            f"{', '.join(sin_origen)}. "
            "Indicá de dónde sale cada una con --col variable=COLUMNA "
            "(valor por contacto) o --valor variable=texto (igual para todos)."
        )

    return origenes


def parsear_asignacion(asignacion, opcion):
    """
    Parte un argumento con formato "variable=valor" de --col o --valor.

    Args:
        asignacion: texto tal como lo pasó el usuario.
        opcion: nombre de la opción ("--col" o "--valor"), para el mensaje
            de error.

    Returns:
        tuple[str, str]: (variable, valor), ambos sin espacios alrededor.

    Raises:
        ValueError: si falta el "=" o el nombre de la variable.
    """
    if "=" not in asignacion:
        raise ValueError(
            f"{opcion} espera el formato variable=valor, se recibió: {asignacion!r}"
        )

    variable, valor = asignacion.split("=", 1)
    variable = variable.strip()

    if not variable:
        raise ValueError(f"{opcion} sin nombre de variable: {asignacion!r}")

    return variable, valor.strip()
