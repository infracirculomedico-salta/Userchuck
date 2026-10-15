"""
Rutas del Dashboard y Mensajería en Vivo.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from portal.auth import obtener_usuario_actual
from portal.database import DBManager
from portal.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/metricas")
def metricas_dashboard(usuario: dict = Depends(obtener_usuario_actual)):
    return DashboardService.obtener_metricas()


@router.get("/mensajes")
def listar_mensajes(
    direccion: Optional[str] = Query(None, description="ENTRANTE o SALIENTE"),
    tipo: Optional[str] = Query(None),
    busqueda: Optional[str] = Query(None),
    limite: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    usuario: dict = Depends(obtener_usuario_actual),
):
    clausulas = []
    params = {}

    if direccion:
        clausulas.append("direccion = :dir")
        params["dir"] = direccion.upper()

    if tipo:
        clausulas.append("tipo_mensaje = :tipo")
        params["tipo"] = tipo

    if busqueda:
        clausulas.append("(wa_id LIKE :q OR wa_name LIKE :q OR texto_mensaje LIKE :q)")
        params["q"] = f"%{busqueda}%"

    where_sql = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""

    sql_or = f"""
        SELECT id_log, fecha_registro, direccion, wa_id, wa_name,
               tipo_mensaje, texto_mensaje, file_id, wsp_msg_id, estado_status
        FROM wsp_log_mensajes
        {where_sql}
        ORDER BY id_log DESC
        OFFSET :offset ROWS FETCH NEXT :limite ROWS ONLY
    """
    sql_sq = f"""
        SELECT id_log, fecha_registro, direccion, wa_id, wa_name,
               tipo_mensaje, texto_mensaje, file_id, wsp_msg_id, estado_status
        FROM wsp_log_mensajes
        {where_sql}
        ORDER BY id_log DESC
        LIMIT :limite OFFSET :offset
    """
    params["offset"] = offset
    params["limite"] = limite

    filas = DBManager.execute_query(sql_or, sql_sq, params)
    for f in filas:
        f["fecha_registro"] = str(f.get("fecha_registro") or "")

    return {"mensajes": filas, "offset": offset, "limite": limite}
