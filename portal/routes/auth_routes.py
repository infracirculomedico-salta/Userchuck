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


import logging
logger = logging.getLogger("portal.auth")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(datos: LoginRequest, response: Response):
    try:
        usuario = autenticar_usuario(datos.username, datos.password)
    except Exception as e:
        logger.exception("Error interno en autenticar_usuario: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error conectando a base de datos: {e}",
        )

    if not usuario:
        logger.warning("Intento de login fallido para usuario: '%s'", datos.username)
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
