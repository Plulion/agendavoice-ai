"""Pure formatting and token validation helpers for appointment confirmation notifications (R5.0.3)."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONFIRMATION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,200}$")


def is_valid_confirmation_token_format(token: str) -> bool:
    """Return True only for URL-safe base64 tokens matching token_urlsafe format."""
    return bool(isinstance(token, str) and CONFIRMATION_TOKEN_RE.fullmatch(token))


def format_appointment_local_time(starts_at_utc: datetime, timezone_name: str) -> str:
    """Format a UTC appointment timestamp in the branch's local IANA timezone."""
    if starts_at_utc.tzinfo is None:
        starts_at_utc = starts_at_utc.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
        timezone_name = "UTC"
    local_dt = starts_at_utc.astimezone(zone)
    offset = local_dt.strftime("%z")
    offset_fmt = f"UTC{offset[:3]}:{offset[3:]}" if len(offset) == 5 else "UTC"
    return f"{local_dt.strftime('%d/%m/%Y %H:%M')} ({timezone_name}, {offset_fmt})"


def resolve_confirmation_recipient(
    *,
    created_new_customer: bool,
    stored_email: str | None,
    requested_email: str | None,
) -> str | None:
    """Determine the safe confirmation recipient email (fixes A2).

    - Brand-new customers use the email provided during registration.
    - Existing customers ALWAYS use their stored email address; callers cannot
      redirect confirmation links or customer PII to an arbitrary email address.
    """
    if created_new_customer:
        return (requested_email or stored_email or "").strip() or None
    return (stored_email or "").strip() or None
