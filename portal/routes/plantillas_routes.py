"""
Rutas de Plantillas de WhatsApp y Previsualización.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from portal.auth import obtener_usuario_actual
from portal.services.plantillas_service import PlantillasService

router = APIRouter(prefix="/api/plantillas", tags=["Plantillas"])


class PrevisualizarRequest(BaseModel):
    nombre_plantilla: str
    valores: dict


@router.get("")
def listar_plantillas(usuario: dict = Depends(obtener_usuario_actual)):
    return PlantillasService.listar_plantillas()


@router.post("/previsualizar")
def previsualizar_plantilla(
    datos: PrevisualizarRequest,
    usuario: dict = Depends(obtener_usuario_actual),
):
    renderizado = PlantillasService.renderizar_previsualizacion(
        datos.nombre_plantilla, datos.valores
    )
    return {
        "plantilla": datos.nombre_plantilla,
        "texto_renderizado": renderizado,
    }


@router.get("/{nombre}/verificar")
def verificar_plantilla_meta(
    nombre: str,
    usuario: dict = Depends(obtener_usuario_actual),
):
    return PlantillasService.consultar_estado_meta(nombre)
