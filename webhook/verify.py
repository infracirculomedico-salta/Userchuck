"""
Validación de la firma HMAC-SHA256 que Meta envía en el header
X-Hub-Signature-256 para el webhook de WhatsApp Business API.

Referencia: https://developers.facebook.com/docs/graph-api/webhooks/getting-started#validating-payloads
"""

import hashlib
import hmac
import os


def verificar_firma(payload_bytes: bytes, firma_header: str | None) -> bool:
    """
    Valida que `payload_bytes` (el body raw del request) coincida con la
    firma HMAC-SHA256 enviada por Meta en el header X-Hub-Signature-256.

    El header llega con el formato "sha256=<hexdigest>".

    Args:
        payload_bytes: cuerpo crudo (raw) del request, sin parsear.
        firma_header: valor del header X-Hub-Signature-256.

    Returns:
        True si la firma es válida, False en cualquier otro caso
        (header ausente, formato inválido, secreto no configurado, o
        firma que no coincide).
    """
    if not firma_header:
        return False

    if not firma_header.startswith("sha256="):
        return False

    firma_recibida = firma_header.removeprefix("sha256=")

    app_secret = os.environ.get("META_APP_SECRET")
    if not app_secret:
        return False

    firma_calculada = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # La comparación va sobre bytes y no sobre str: compare_digest lanza
    # TypeError si alguno de los dos str tiene caracteres no-ASCII, y el
    # header lo controla quien manda el request. Esa excepción está fuera
    # del try de recibir_evento, así que cualquiera podría provocar un
    # 500 mandando un header con un acento. En bytes no puede pasar, y la
    # comparación sigue siendo de tiempo constante.
    return hmac.compare_digest(
        firma_calculada.encode("ascii"),
        firma_recibida.encode("utf-8", errors="ignore"),
    )
