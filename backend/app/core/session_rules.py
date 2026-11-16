"""Reglas puras de sesiones (R4.2.2), sin dependencias externas."""
from datetime import datetime, timezone

# Ventana en la que un refresh token ya rotado se considera renovación concurrente
# (dos pestañas o dos peticiones casi simultáneas), no robo.
REUSE_GRACE_SECONDS = 15


def is_concurrent_reuse(revoked_at: datetime | None, now: datetime,
                        grace_seconds: int = REUSE_GRACE_SECONDS) -> bool:
    """True si el token se revocó hace poco: se rechaza sin cerrar todas las sesiones."""
    if revoked_at is None:
        return False
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed = (now - revoked_at).total_seconds()
    return 0 <= elapsed <= grace_seconds
