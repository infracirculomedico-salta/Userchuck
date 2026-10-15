"""
Servicio de Gestión y Previsualización de Plantillas de WhatsApp (Meta).
"""

import logging
import re
import sys
from pathlib import Path
import requests

from portal.config import META_ACCESS_TOKEN, META_API_VERSION, PROJECT_ROOT

# Importar las definiciones de plantillas existentes en sender
sys.path.insert(0, str(PROJECT_ROOT / "sender"))
try:
    from plantillas import PLANTILLAS as PLANTILLAS_CONFIG, obtener_plantilla
except ImportError:
    PLANTILLAS_CONFIG = {}

logger = logging.getLogger("portal.plantillas")

# Plantillas con sus textos aprobados oficiales de Meta (es_AR)
PLANTILLAS_TEXTOS = {
    "notificacion_liquidacion": {
        "titulo": "Notificación de Liquidación",
        "cuerpo": (
            "Estimado/a Dr./Dra. {{nombre}},\n\n"
            "Le informamos que su liquidación correspondiente al período {{periodo}} se encuentra disponible para su consulta.\n\n"
            "Monto liquidado: ${{monto}}\n\n"
            "Para acceder al detalle, ingrese al portal del Círculo Médico o comuníquese con administración.\n\n"
            "Atentamente,\n"
            "Círculo Médico de Salta"
        ),
        "ejemplo": {
            "nombre": "Juan Pérez",
            "periodo": "Agosto 2026",
            "monto": "185.400",
        },
    },
    "confirmacion_recepcion_solicitud": {
        "titulo": "Confirmación de Recepción de Solicitud",
        "cuerpo": (
            "Hola {{nombre}}.\n\n"
            "Confirmamos la recepción de tu solicitud correspondiente a {{tramite}}.\n\n"
            "Nuestro equipo ya se encuentra gestionándola.\n\n"
            "Te informaremos cualquier novedad por este mismo medio."
        ),
        "ejemplo": {
            "nombre": "María Eugenia Martínez",
            "tramite": "reempadronamiento",
        },
    },
    "solicitud_documentacion": {
        "titulo": "Solicitud de Documentación",
        "cuerpo": (
            "Hola {{nombre}}.\n\n"
            "Para continuar con la gestión de {{tramite}}, necesitamos que nos envíes la siguiente documentación:\n\n"
            "{{documentacion}}\n\n"
            "Podés responder este mensaje adjuntando los archivos solicitados.\n\n"
            "Muchas gracias."
        ),
        "ejemplo": {
            "nombre": "Juan Pablo Rodríguez",
            "tramite": "reempadronamiento",
            "documentacion": "DNI y matrícula profesional",
        },
    },
    "aviso_suspension_prestacion": {
        "titulo": "Aviso de Suspensión de Prestación",
        "cuerpo": (
            "Hola, {{nombre}}. Te informamos que de manera temporal y hasta nuevo aviso, hay una prestación con disponibilidad limitada.\n\n"
            "Para más información, comunicate con nuestro Centro de Atención al Socio a través de los canales habituales."
        ),
        "ejemplo": {
            "nombre": "Ana Laura López",
        },
    },
    "aviso_institucional_general": {
        "titulo": "Aviso Institucional General",
        "cuerpo": (
            "Estimado/a {{nombre}},\n\n"
            "Le informamos que {{detalle_aviso}}.\n\n"
            "Para consultas, comuníquese con el Círculo Médico de Salta a través de nuestros canales oficiales.\n\n"
            "Atentamente,\n"
            "Círculo Médico de Salta"
        ),
        "ejemplo": {
            "nombre": "Marcelo Eduardo Pereyra",
            "detalle_aviso": "la sede permanecerá cerrada el próximo lunes por feriado",
        },
    },
    "bienvenida_menu_principal": {
        "titulo": "Bienvenida y Menú Principal",
        "cuerpo": (
            "Hola.\n\n"
            "¡Bienvenido/a al Círculo Médico de Salta!\n\n"
            "Este canal se utiliza para enviarte comunicaciones institucionales, avisos y novedades. Para consultas o gestiones, comunicate con nosotros a través de nuestros canales de atención habituales.\n\n"
            "Gracias por formar parte del Círculo Médico de Salta."
        ),
        "ejemplo": {},
    },
}


class PlantillasService:
    @classmethod
    def listar_plantillas(cls) -> list[dict]:
        """Devuelve el catálogo de plantillas con metadatos y ejemplos."""
        resultado = []
        for clave, config in PLANTILLAS_CONFIG.items():
            texto_info = PLANTILLAS_TEXTOS.get(clave, {
                "titulo": clave.replace("_", " ").title(),
                "cuerpo": "",
                "ejemplo": {},
            })
            item = {
                "id": clave,
                "nombre": clave,
                "titulo": texto_info["titulo"],
                "id_meta": config.get("id_meta"),
                "categoria": config.get("categoria"),
                "formato": config.get("formato"),
                "idioma": config.get("idioma", "es_AR"),
                "variables": config.get("variables", []),
                "descripcion": config.get("descripcion", ""),
                "cuerpo": texto_info["cuerpo"],
                "ejemplo": texto_info["ejemplo"],
            }
            resultado.append(item)
        return resultado

    @classmethod
    def renderizar_previsualizacion(cls, nombre_plantilla: str, valores: dict) -> str:
        """Renderiza el texto de una plantilla reemplazando {{variable}} con valores."""
        info = PLANTILLAS_TEXTOS.get(nombre_plantilla)
        if not info:
            return ""

        texto = info["cuerpo"]
        for var, val in valores.items():
            valor_str = str(val or f"[{var}]")
            texto = texto.replace(f"{{{{{var}}}}}", valor_str)

        # Si quedaron variables sin reemplazar, marcarlas
        texto = re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", r"[\1]", texto)
        return texto

    @classmethod
    def consultar_estado_meta(cls, nombre_plantilla: str) -> dict:
        """Consulta en vivo a la Graph API de Meta el estado de una plantilla."""
        config = PLANTILLAS_CONFIG.get(nombre_plantilla)
        if not config or not config.get("id_meta"):
            return {"error": "Plantilla no encontrada en registro local"}

        id_meta = config["id_meta"]
        url = f"https://graph.facebook.com/{META_API_VERSION}/{id_meta}"
        params = {"fields": "name,language,status,category,components"}
        headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}

        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {
                    "ok": True,
                    "status": data.get("status"),
                    "name": data.get("name"),
                    "category": data.get("category"),
                    "language": data.get("language"),
                }
            else:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
