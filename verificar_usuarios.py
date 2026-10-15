"""
Script de diagnóstico y reparación de usuarios en Oracle / SQLite.
Uso en OCI:
    /opt/userchuck/venv311/bin/python /opt/userchuck/verificar_usuarios.py
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Auto-ejecución con el entorno virtual si se invocó con el python del sistema
venv_oci = Path("/opt/userchuck/venv311/bin/python")
venv_win = ROOT / ".venv" / "Scripts" / "python.exe"
venv_local = ROOT / ".venv" / "bin" / "python"
venv_target = venv_oci if venv_oci.exists() else (venv_win if venv_win.exists() else (venv_local if venv_local.exists() else None))

if venv_target and Path(sys.executable).resolve() != venv_target.resolve():
    sys.exit(subprocess.call([str(venv_target), str(ROOT / "verificar_usuarios.py"), *sys.argv[1:]]))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "sender") not in sys.path:
    sys.path.insert(0, str(ROOT / "sender"))

from portal.database import DBManager, hash_password
from portal.auth import autenticar_usuario, obtener_usuario_por_username


def main():
    print("=" * 65)
    print("  DIAGNÓSTICO DE BASE DE DATOS Y USUARIOS — PORTAL CMS")
    print("=" * 65)

    es_oracle = DBManager.is_oracle()
    print(f"Motor activo: {'Oracle (OCI)' if es_oracle else 'SQLite (Local)'}")

    # 1. Comprobar tabla
    print("\n1. Verificando tabla WSP_USUARIOS...")
    sql_check = "SELECT COUNT(*) as cant FROM wsp_usuarios"
    try:
        res = DBManager.execute_query(sql_check, sql_check)
        total_usuarios = res[0].get("cant", 0) if res else 0
        print(f"   [OK] Tabla WSP_USUARIOS accesible. Cantidad de usuarios: {total_usuarios}")
    except Exception as e:
        print(f"   [ERROR] No se pudo consultar WSP_USUARIOS: {e}")
        print("\n   Posible causa en Oracle: la tabla wsp_usuarios no fue creada o pertenece a otro esquema.")
        return

    # 2. Listar usuarios existentes
    print("\n2. Usuarios en la base de datos:")
    sql_list = "SELECT id_usuario, username, rol, activo, password_salt, password_hash FROM wsp_usuarios"
    try:
        usuarios = DBManager.execute_query(sql_list, sql_list)
        if not usuarios:
            print("   (La tabla está vacía)")
        for u in usuarios:
            print(f"   - ID: {u.get('id_usuario')} | Usuario: '{u.get('username')}' | Rol: {u.get('rol')} | Activo: {u.get('activo')}")
    except Exception as e:
        print(f"   [ERROR] Listando usuarios: {e}")

    # 3. Probar autenticación o reparar
    print("\n3. Probando autenticación:")
    for user_test, pass_test in [("admin", "admin123"), ("operador", "operador123")]:
        try:
            auth_ok = autenticar_usuario(user_test, pass_test)
            if auth_ok:
                print(f"   [OK] '{user_test}' autenticado exitosamente como {auth_ok.get('rol')}")
            else:
                print(f"   [FALLO] No se pudo autenticar '{user_test}' con '{pass_test}'. Reparando...")
                h, s = hash_password(pass_test)
                # Intentar update
                sql_up = "UPDATE wsp_usuarios SET password_hash = :h, password_salt = :s, activo = 1 WHERE LOWER(username) = :u"
                filas = DBManager.execute_update(sql_up, sql_up, {"h": h, "s": s, "u": user_test})
                if filas == 0:
                    # Intentar insert
                    sql_in = "INSERT INTO wsp_usuarios (username, nombre_completo, email, rol, password_hash, password_salt, activo) VALUES (:u, :nom, :em, :rol, :h, :s, 1)"
                    DBManager.execute_update(sql_in, sql_in, {
                        "u": user_test,
                        "nom": "Administrador CMS" if user_test == "admin" else "Operador CMS",
                        "em": f"{user_test}@cirmedsa.org.ar",
                        "rol": "ADMIN" if user_test == "admin" else "OPERADOR",
                        "h": h,
                        "s": s
                    })
                print(f"   [REPARADO] Usuario '{user_test}' actualizado con contraseña '{pass_test}'.")
        except Exception as e:
            print(f"   [ERROR] en prueba de '{user_test}': {e}")

    print("\n" + "=" * 65)
    print("Diagnóstico finalizado.")
    print("=" * 65)


if __name__ == "__main__":
    main()
