"""
Servicio de Gestión de Usuarios y Roles del Portal (ADMIN / OPERADOR).
"""

import logging
from typing import Optional

from portal.database import DBManager, hash_password

logger = logging.getLogger("portal.usuarios")


class UsuariosService:
    @classmethod
    def listar_usuarios(cls) -> list[dict]:
        """Devuelve todos los usuarios registrados."""
        sql_or = """
            SELECT id_usuario, username, nombre_completo, email, rol, activo,
                   ultimo_acceso, fecha_creacion
            FROM wsp_usuarios
            ORDER BY id_usuario ASC
        """
        sql_sq = """
            SELECT id_usuario, username, nombre_completo, email, rol, activo,
                   ultimo_acceso, fecha_creacion
            FROM wsp_usuarios
            ORDER BY id_usuario ASC
        """
        filas = DBManager.execute_query(sql_or, sql_sq)
        for f in filas:
            f["activo"] = bool(f.get("activo"))
            f["ultimo_acceso"] = str(f.get("ultimo_acceso") or "Nunca")
            f["fecha_creacion"] = str(f.get("fecha_creacion") or "")
        return filas

    @classmethod
    def crear_usuario(
        cls,
        username: str,
        nombre_completo: str,
        email: str,
        rol: str,
        password: str,
    ) -> dict:
        """Crea un nuevo usuario en la base de datos."""
        username_limpio = username.strip().lower()
        if len(username_limpio) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
        if len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres")

        rol_normalizado = rol.upper()
        if rol_normalizado not in ("ADMIN", "OPERADOR"):
            rol_normalizado = "OPERADOR"

        # Verificar si ya existe
        sql_check = "SELECT COUNT(*) as count FROM wsp_usuarios WHERE LOWER(username) = :u"
        filas = DBManager.execute_query(sql_check, sql_check, {"u": username_limpio})
        if filas and filas[0].get("count", 0) > 0:
            raise ValueError(f"El usuario '{username_limpio}' ya existe")

        pw_hash, pw_salt = hash_password(password)

        sql_or = """
            INSERT INTO wsp_usuarios (username, nombre_completo, email, rol, password_hash, password_salt, activo, fecha_creacion)
            VALUES (:usr, :nom, :em, :rol, :hsh, :slt, 1, SYSTIMESTAMP)
        """
        sql_sq = """
            INSERT INTO wsp_usuarios (username, nombre_completo, email, rol, password_hash, password_salt, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """
        DBManager.execute_update(sql_or, sql_sq, (
            username_limpio, nombre_completo.strip(), email.strip(), rol_normalizado,
            pw_hash, pw_salt
        ))

        return {
            "username": username_limpio,
            "nombre_completo": nombre_completo,
            "email": email,
            "rol": rol_normalizado,
        }

    @classmethod
    def actualizar_usuario(
        cls,
        id_usuario: int,
        nombre_completo: str,
        email: str,
        rol: str,
        activo: bool,
        password: Optional[str] = None,
    ) -> bool:
        """Actualiza datos de un usuario y opcionalmente su clave."""
        rol_normalizado = rol.upper() if rol.upper() in ("ADMIN", "OPERADOR") else "OPERADOR"
        activo_int = 1 if activo else 0

        if password and len(password) >= 6:
            pw_hash, pw_salt = hash_password(password)
            sql_or = """
                UPDATE wsp_usuarios
                SET nombre_completo = :nom, email = :em, rol = :rol, activo = :act,
                    password_hash = :hsh, password_salt = :slt
                WHERE id_usuario = :id
            """
            sql_sq = """
                UPDATE wsp_usuarios
                SET nombre_completo = ?, email = ?, rol = ?, activo = ?,
                    password_hash = ?, password_salt = ?
                WHERE id_usuario = ?
            """
            DBManager.execute_update(sql_or, sql_sq, (
                nombre_completo.strip(), email.strip(), rol_normalizado, activo_int,
                pw_hash, pw_salt, id_usuario
            ))
        else:
            sql_or = """
                UPDATE wsp_usuarios
                SET nombre_completo = :nom, email = :em, rol = :rol, activo = :act
                WHERE id_usuario = :id
            """
            sql_sq = """
                UPDATE wsp_usuarios
                SET nombre_completo = ?, email = ?, rol = ?, activo = ?
                WHERE id_usuario = ?
            """
            DBManager.execute_update(sql_or, sql_sq, (
                nombre_completo.strip(), email.strip(), rol_normalizado, activo_int, id_usuario
            ))
        return True
