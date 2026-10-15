"""
Script de inicio rápido para el Portal de WhatsApp del Círculo Médico de Salta.
Uso: python iniciar_portal.py
"""

import sys
import uvicorn
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "sender") not in sys.path:
    sys.path.insert(0, str(ROOT / "sender"))

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Portal WhatsApp Business — Círculo Médico de Salta")
    print("=" * 60)
    print("  Iniciando servidor web en: http://localhost:8007")
    print("  Acceso inicial:")
    print("    - Admin:    admin / admin123")
    print("    - Operador: operador / operador123")
    print("=" * 60 + "\n")

    uvicorn.run("portal.main:app", host="0.0.0.0", port=8007, reload=True)
