"""
Rutas de Contactos y Padrón de Socios CMS.
"""

from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from portal.auth import obtener_usuario_actual
from portal.services.contactos_service import ContactosService

router = APIRouter(prefix="/api/contactos", tags=["Contactos"])


@router.get("/archivos")
def listar_archivos_csv(usuario: dict = Depends(obtener_usuario_actual)):
    return ContactosService.listar_archivos()


@router.get("/resumen")
def resumen_archivo(archivo: str = Query(..., description="Nombre del archivo CSV"), usuario: dict = Depends(obtener_usuario_actual)):
    try:
        return ContactosService.obtener_resumen_csv(archivo)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/filas")
def listar_contactos(
    archivo: str = Query(...),
    consentimiento: Optional[str] = Query(None, description="ACEPTO o NO ACEPTO"),
    busqueda: Optional[str] = Query(None),
    limite: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    usuario: dict = Depends(obtener_usuario_actual),
):
    try:
        return ContactosService.leer_filas_csv(
            nombre_archivo=archivo,
            filtro_consentimiento=consentimiento,
            busqueda=busqueda,
            limite=limite,
            offset=offset,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/subir")
async def subir_csv(
    archivo: UploadFile = File(...),
    usuario: dict = Depends(obtener_usuario_actual),
):
    if not archivo.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos con extensión .csv")

    try:
        contenido = await archivo.read()
        nombre_guardado = ContactosService.guardar_archivo_csv(archivo.filename, contenido)
        resumen = ContactosService.obtener_resumen_csv(nombre_guardado)
        return {
            "ok": True,
            "mensaje": f"Archivo '{nombre_guardado}' cargado y validado exitosamente.",
            "resumen": resumen,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error validando archivo: {e}")
