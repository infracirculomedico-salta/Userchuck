"""
Script de gestión para el Portal WhatsApp - Círculo Médico de Salta.
Permite iniciar el servidor con el comando habitual:
    py manage.py runserver
    python manage.py runserver 8000
    python manage.py runserver 0.0.0.0:8000
"""

import os
import subprocess
import sys
from pathlib import Path

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent

# Si existe un entorno virtual local (.venv), auto-ejecutarse con él
venv_python_win = BASE_DIR / ".venv" / "Scripts" / "python.exe"
venv_python_linux = BASE_DIR / ".venv" / "bin" / "python"
venv_target = venv_python_win if venv_python_win.exists() else (venv_python_linux if venv_python_linux.exists() else None)

if venv_target and Path(sys.executable).resolve() != venv_target.resolve():
    # Re-ejecutar automáticamente dentro del venv
    resultado = subprocess.call([str(venv_target), str(BASE_DIR / "manage.py"), *sys.argv[1:]])
    sys.exit(resultado)

# Asegurar rutas en sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "sender") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "sender"))


def main():
    args = sys.argv[1:]
    comando = args[0] if args else "runserver"

    if comando == "runserver":
        host = "127.0.0.1"
        port = 8000

        # Parsear argumentos opcionales como 8000 o 0.0.0.0:8000
        if len(args) > 1:
            val = args[1]
            if ":" in val:
                h, p = val.split(":", 1)
                if h:
                    host = h
                if p.isdigit():
                    port = int(p)
            elif val.isdigit():
                port = int(val)

        print("\n" + "=" * 65)
        print("  PORTAL WHATSAPP BUSINESS — CÍRCULO MÉDICO DE SALTA")
        print("=" * 65)
        print(f"  Servidor iniciado exitosamente en: http://{host}:{port}/")
        print("  Abre tu navegador en la URL anterior.")
        print("")
        print("  Credenciales de acceso inicial:")
        print("    * Administrador: admin / admin123")
        print("    * Operador:      operador / operador123")
        print("=" * 65)
        print("  Presiona CTRL+C para detener el servidor.\n")

        try:
            import uvicorn
        except ImportError:
            print("[ERROR] uvicorn no está instalado en este entorno de Python.")
            print("Ejecuta: pip install -r requirements.txt")
            sys.exit(1)

        uvicorn.run("portal.main:app", host=host, port=port, reload=True)

    elif comando in ("help", "--help", "-h"):
        print("\nUso del Portal WhatsApp CMS:")
        print("  py manage.py runserver               -> Inicia el servidor en el puerto 8000")
        print("  py manage.py runserver 8080          -> Inicia en el puerto 8080")
        print("  py manage.py runserver 0.0.0.0:8000  -> Inicia escuchando en todas las interfaces")
        print("")

    else:
        print(f"\nComando '{comando}' no reconocido.")
        print("Para iniciar el servidor ejecuta: py manage.py runserver\n")


if __name__ == "__main__":
    main()
