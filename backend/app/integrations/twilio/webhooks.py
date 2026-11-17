"""Secure WhatsApp and Voice webhook adapters for Twilio / Meta Cloud API (R4.3.0).

Includes:
- Cryptographic HMAC-SHA1 verification (`X-Twilio-Signature`) when `TWILIO_AUTH_TOKEN` is configured.
- Prefix normalization (`whatsapp:+569...`) to extract the verified sender phone number.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Mapping

from app.modules.customers.visibility import normalize_phone


def extract_channel_and_phone(raw_from: str) -> tuple[str, str]:
    """Extract ('WHATSAPP' | 'VOICE', '+569...') from the Twilio/Meta From field."""
    val = (raw_from or "").strip()
    if val.lower().startswith("whatsapp:"):
        raw_num = val.split(":", 1)[1]
        return "WHATSAPP", normalize_phone(raw_num)
    return "VOICE", normalize_phone(val)


def verify_twilio_signature(url: str, params: Mapping[str, str], signature: str, auth_token: str) -> bool:
    """Validate the Twilio HMAC-SHA1 signature to reject forged webhook requests."""
    if not auth_token or not signature:
        return False
    concatenated = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    digest = hmac.new(auth_token.encode("utf-8"), concatenated.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature.strip())
