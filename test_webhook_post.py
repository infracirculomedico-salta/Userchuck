"""
Script de prueba local para el webhook de WhatsApp (POST /webhook).

Arma un payload realista de tipo "message_status" (como lo manda Meta),
calcula la firma HMAC-SHA256 con META_APP_SECRET usando el mismo formato
que espera webhook/verify.py, y hace el POST contra el servidor local.

Solo para testing local, no se usa en producción.

Uso:
    1. Levantar el servidor:
         source venv311/bin/activate
         uvicorn webhook.main:app --reload --port 8000
    2. En otra terminal:
         source venv311/bin/activate
         python test_webhook_post.py
"""

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path("/opt/userchuck/config")
load_dotenv(CONFIG_DIR / "meta.env")

WEBHOOK_URL = "http://localhost:8000/webhook"

APP_SECRET = os.environ.get("META_APP_SECRET")
if not APP_SECRET:
    raise SystemExit("META_APP_SECRET no está definido en config/meta.env")

# Payload de ejemplo: un evento de status de mensaje (message_status),
# con la estructura real que envía la WhatsApp Cloud API de Meta.
payload = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550001111",
                            "phone_number_id": "123456789012345",
                        },
                        "statuses": [
                            {
                                "id": "wamid.HBgLMTU1NTAwMDExMTEVAgARGBI5QTNDQTVBRUNGRjM5RkQ0RgA=",
                                "status": "delivered",
                                "timestamp": "1735339200",
                                "recipient_id": "5215500001111",
                                "conversation": {
                                    "id": "d9b3d5f2c1a4e6b7f8091a2b3c4d5e6f",
                                    "origin": {"type": "business_initiated"},
                                },
                                "pricing": {
                                    "billable": True,
                                    "pricing_model": "CBP",
                                    "category": "business_initiated",
                                },
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

# Se serializa una sola vez: los mismos bytes se firman y se envían,
# tal como el servidor los va a recibir y firmar para comparar.
payload_bytes = json.dumps(payload).encode("utf-8")

firma = hmac.new(
    key=APP_SECRET.encode("utf-8"),
    msg=payload_bytes,
    digestmod=hashlib.sha256,
).hexdigest()
firma_header = f"sha256={firma}"

request = urllib.request.Request(
    WEBHOOK_URL,
    data=payload_bytes,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": firma_header,
    },
)

try:
    with urllib.request.urlopen(request) as response:
        print(response.status)
except urllib.error.HTTPError as e:
    # También es una respuesta válida del servidor (ej: 403 por firma inválida)
    print(e.code)
except urllib.error.URLError as e:
    print(f"No se pudo conectar a {WEBHOOK_URL}: {e.reason}")
