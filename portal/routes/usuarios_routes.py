"""
Rutas de Gestión de Usuarios del Sistema (Requiere ADMIN).
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from portal.auth import requerir_admin
from portal.services.usuarios_service import UsuariosService

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"])


class CrearUsuarioRequest(BaseModel):
    username: str
    nombre_completo: str
    email: str
    rol: str = "OPERADOR"
    password: str


class ActualizarUsuarioRequest(BaseModel):
    nombre_completo: str
    email: str
    rol: str
    activo: bool
    password: Optional[str] = None


@router.get("")
def listar_usuarios(admin_user: dict = Depends(requerir_admin)):
    return UsuariosService.listar_usuarios()


@router.post("")
def crear_usuario(
    datos: CrearUsuarioRequest,
    admin_user: dict = Depends(requerir_admin),
):
    try:
        return UsuariosService.crear_usuario(
            username=datos.username,
            nombre_completo=datos.nombre_completo,
            email=datos.email,
            rol=datos.rol,
            password=datos.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{id_usuario}")
def actualizar_usuario(
    id_usuario: int,
    datos: ActualizarUsuarioRequest,
    admin_user: dict = Depends(requerir_admin),
):
    try:
        UsuariosService.actualizar_usuario(
            id_usuario=id_usuario,
            nombre_completo=datos.nombre_completo,
            email=datos.email,
            rol=datos.rol,
            activo=datos.activo,
            password=datos.password,
        )
        return {"ok": True, "mensaje": "Usuario actualizado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
