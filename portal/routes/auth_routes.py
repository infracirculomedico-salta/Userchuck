"""
Rutas de Autenticación y Control de Sesión.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from portal.auth import (
    autenticar_usuario,
    crear_token_sesion,
    obtener_usuario_actual,
)
from portal.config import SESSION_COOKIE_NAME, SESSION_DURATION_HOURS

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(datos: LoginRequest, response: Response):
    usuario = autenticar_usuario(datos.username, datos.password)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    token = crear_token_sesion(usuario)

    # Establecer cookie segura
    max_age = SESSION_DURATION_HOURS * 3600
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )

    return {
        "ok": True,
        "token": token,
        "usuario": {
            "id": usuario["id_usuario"],
            "username": usuario["username"],
            "nombre": usuario["nombre_completo"],
            "email": usuario.get("email"),
            "rol": usuario["rol"],
        },
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"ok": True, "mensaje": "Sesión finalizada"}


@router.get("/me")
def perfil_actual(usuario: dict = Depends(obtener_usuario_actual)):
    return {
        "id": usuario["id_usuario"],
        "username": usuario["username"],
        "nombre": usuario["nombre_completo"],
        "email": usuario.get("email"),
        "rol": usuario["rol"],
    }
