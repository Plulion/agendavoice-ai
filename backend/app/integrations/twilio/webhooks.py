"""Adaptadores seguros para webhooks de WhatsApp y Voz vía Twilio / Meta Cloud API (R4.3.0).

Incluye:
- Verificación criptográfica HMAC-SHA1 (`X-Twilio-Signature`) cuando `TWILIO_AUTH_TOKEN` está activo.
- Limpieza de prefijos `whatsapp:+569...` para identificar el teléfono real verificado del remitente.
- Resolución de la sucursal de destino por su número telefónico (`Branch.phone`).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Mapping

from app.modules.customers.visibility import normalize_phone


def extract_channel_and_phone(raw_from: str) -> tuple[str, str]:
    """Extrae ('WHATSAPP' | 'VOICE', '+569...') desde el campo From de Twilio/Meta."""
    val = (raw_from or "").strip()
    if val.lower().startswith("whatsapp:"):
        raw_num = val.split(":", 1)[1]
        return "WHATSAPP", normalize_phone(raw_num)
    return "VOICE", normalize_phone(val)


def verify_twilio_signature(url: str, params: Mapping[str, str], signature: str, auth_token: str) -> bool:
    """Valida la firma HMAC-SHA1 de Twilio para impedir webhooks falsificados."""
    if not auth_token or not signature:
        return False
    concatenated = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    digest = hmac.new(auth_token.encode("utf-8"), concatenated.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature.strip())
