"""
Rutas de la API para Envío de Mensajes y Gestión de Conversaciones en Tiempo Real.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from portal.auth import obtener_usuario_actual
from portal.services.mensajes_service import MensajesService

logger = logging.getLogger("portal.mensajes")
router = APIRouter(prefix="/api/mensajes", tags=["Mensajería"])


class ResponderMensajeRequest(BaseModel):
    wa_id: str
    texto: str = ""
    wsp_msg_id_contexto: Optional[str] = None
    tipo_envio: str = "texto"
    nombre_plantilla: Optional[str] = None
    parametros_plantilla: Optional[dict] = None


@router.get("/conversaciones")
def listar_conversaciones(
    busqueda: Optional[str] = Query(default=None, description="Término de búsqueda"),
    filtro: Optional[str] = Query(default=None, description="Filtro: recibidos, pendientes, todos"),
    usuario: dict = Depends(obtener_usuario_actual),
):
    """Retorna la lista de conversaciones y mensajes recibidos."""
    try:
        b = str(busqueda) if busqueda and isinstance(busqueda, str) else None
        f = str(filtro) if filtro and isinstance(filtro, str) else None
        conversaciones = MensajesService.obtener_conversaciones(busqueda=b, filtro=f)
        return {
            "conversaciones": conversaciones,
            "total": len(conversaciones),
        }
    except Exception as e:
        logger.exception("Error listando conversaciones: %s", e)
        raise HTTPException(status_code=500, detail=f"Error obteniendo conversaciones: {e}")


@router.get("/conversacion/{wa_id}")
def ver_conversacion(
    wa_id: str,
    usuario: dict = Depends(obtener_usuario_actual),
):
    """Retorna el historial completo de mensajes para un contacto específico."""
    try:
        data = MensajesService.obtener_conversacion(wa_id)
        return data
    except Exception as e:
        logger.exception("Error obteniendo conversación para wa_id=%s: %s", wa_id, e)
        raise HTTPException(status_code=500, detail=f"Error obteniendo historial: {e}")


@router.post("/responder")
def responder_mensaje(
    datos: ResponderMensajeRequest,
    usuario: dict = Depends(obtener_usuario_actual),
):
    """Envía una respuesta de texto libre o plantilla oficial al socio."""
    try:
        resultado = MensajesService.enviar_respuesta(
            wa_id=datos.wa_id,
            texto=datos.texto,
            usuario_actual=usuario.get("username", "operador"),
            wsp_msg_id_contexto=datos.wsp_msg_id_contexto,
            tipo_envio=datos.tipo_envio,
            nombre_plantilla=datos.nombre_plantilla,
            parametros_plantilla=datos.parametros_plantilla,
        )
        if not resultado.get("ok"):
            # Si falla por límite de 24h, devolver 400 con indicador
            return {
                "ok": False,
                "error": resultado.get("error"),
                "es_error_24h": resultado.get("es_error_24h", False),
            }
        return resultado
    except Exception as e:
        logger.exception("Error enviando respuesta a %s: %s", datos.wa_id, e)
        raise HTTPException(status_code=500, detail=f"Error al enviar respuesta: {e}")
