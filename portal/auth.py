"""
Sistema de Autenticación y Autorización del Portal WhatsApp.
"""

import base64
import hmac
import json
import time
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from portal.config import SECRET_KEY, SESSION_COOKIE_NAME, SESSION_DURATION_HOURS
from portal.database import DBManager, hash_password, verify_password

security_bearer = HTTPBearer(auto_error=False)


def firmar_token(payload: dict) -> str:
    """Genera token firmado criptográficamente con HMAC-SHA256."""
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    firma = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), "sha256").hexdigest()
    return f"{payload_b64}.{firma}"


def verificar_token(token: str) -> Optional[dict]:
    """Valida token y comprueba expiración."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, firma = token.rsplit(".", 1)
        firma_esperada = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), "sha256").hexdigest()
        if not hmac.compare_digest(firma, firma_esperada):
            return None
        # Rellenar padding Base64
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        payload = json.loads(payload_json)
        if payload.get("exp", 0) < time.time():
            return None  # Expirado
        return payload
    except Exception:
        return None


def crear_token_sesion(usuario: dict) -> str:
    """Genera token de sesión para un usuario autenticado."""
    exp = int(time.time()) + (SESSION_DURATION_HOURS * 3600)
    payload = {
        "sub": usuario["username"],
        "id": usuario["id_usuario"],
        "nombre": usuario["nombre_completo"],
        "email": usuario.get("email"),
        "rol": usuario["rol"],
        "exp": exp,
    }
    return firmar_token(payload)


def obtener_usuario_por_username(username: str) -> Optional[dict]:
    """Obtiene usuario desde la base de datos (Oracle o SQLite)."""
    sql_oracle = "SELECT id_usuario, username, nombre_completo, email, rol, password_hash, password_salt, activo FROM wsp_usuarios WHERE username = :u"
    sql_sqlite = "SELECT id_usuario, username, nombre_completo, email, rol, password_hash, password_salt, activo FROM wsp_usuarios WHERE username = :u"
    filas = DBManager.execute_query(sql_oracle, sql_sqlite, {"u": username})
    return filas[0] if filas else None


def autenticar_usuario(username: str, password: str) -> Optional[dict]:
    """Verifica credenciales de acceso."""
    user = obtener_usuario_por_username(username.strip())
    if not user:
        return None
    if not user.get("activo"):
        return None
    if not verify_password(password, user["password_salt"], user["password_hash"]):
        return None

    # Registrar último acceso
    sql_oracle = "UPDATE wsp_usuarios SET ultimo_acceso = SYSTIMESTAMP WHERE id_usuario = :id"
    sql_sqlite = "UPDATE wsp_usuarios SET ultimo_acceso = CURRENT_TIMESTAMP WHERE id_usuario = :id"
    DBManager.execute_update(sql_oracle, sql_sqlite, {"id": user["id_usuario"]})

    return user


async def obtener_usuario_actual(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> dict:
    """Dependency para proteger endpoints requiriendo sesión válida."""
    token = None
    # 1. Chequear cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        token = cookie_token
    # 2. Chequear Header Authorization
    elif auth_header:
        token = auth_header.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no iniciada",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verificar_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o inválida",
        )

    usuario = obtener_usuario_por_username(payload["sub"])
    if not usuario or not usuario.get("activo"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado",
        )

    return usuario


async def requerir_admin(usuario: dict = Depends(obtener_usuario_actual)) -> dict:
    """Dependency que restringe el acceso solo a Administradores."""
    if usuario.get("rol") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a Administradores",
        )
    return usuario
