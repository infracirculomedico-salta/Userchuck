"""
Rutas de Campañas, Simulaciones y Disparo de Envíos.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from portal.auth import obtener_usuario_actual
from portal.services.campanas_service import CampanasService

logger = logging.getLogger("portal.campanas")
router = APIRouter(prefix="/api/campanas", tags=["Campañas"])


class SimularCampanaRequest(BaseModel):
    nombre_plantilla: str
    archivo_csv: str
    columnas_mapeadas: dict = {}
    valores_fijos: dict = {}


class EjecutarCampanaRequest(BaseModel):
    nombre_campana: str
    nombre_plantilla: str
    archivo_csv: str
    columnas_mapeadas: dict = {}
    valores_fijos: dict = {}
    pausa_segundos: float = 0.2


@router.get("")
def listar_campanas(usuario: dict = Depends(obtener_usuario_actual)):
    return CampanasService.listar_campanas()


@router.post("/simular")
def simular_campana(
    datos: SimularCampanaRequest,
    usuario: dict = Depends(obtener_usuario_actual),
):
    resultado = CampanasService.simular_campana(
        nombre_plantilla=datos.nombre_plantilla,
        archivo_csv=datos.archivo_csv,
        columnas_mapeadas=datos.columnas_mapeadas,
        valores_fijos=datos.valores_fijos,
    )
    if not resultado.get("ok"):
        raise HTTPException(status_code=400, detail=resultado.get("error", "Error en simulación"))
    return resultado


@router.post("/enviar")
def ejecutar_campana(
    datos: EjecutarCampanaRequest,
    usuario: dict = Depends(obtener_usuario_actual),
):
    try:
        resultado = CampanasService.ejecutar_campana(
            nombre_campana=datos.nombre_campana,
            nombre_plantilla=datos.nombre_plantilla,
            archivo_csv=datos.archivo_csv,
            columnas_mapeadas=datos.columnas_mapeadas,
            valores_fijos=datos.valores_fijos,
            usuario_actual=usuario.get("username", "sistema"),
            pausa_segundos=datos.pausa_segundos,
        )
        if not resultado.get("ok"):
            raise HTTPException(status_code=400, detail=resultado.get("error", "Error ejecutando campaña"))
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error inesperado ejecutando campaña: %s", e)
        raise HTTPException(status_code=500, detail=f"Error en servidor al ejecutar campaña: {e}")


@router.get("/logs/{nombre_log}")
def ver_detalle_log(
    nombre_log: str,
    usuario: dict = Depends(obtener_usuario_actual),
):
    return CampanasService.ver_log_detalle(nombre_log)
