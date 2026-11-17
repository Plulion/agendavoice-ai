"""Pure session rotation rules (R4.2.2+), free of external dependencies."""
from datetime import datetime, timezone

# Grace window (in seconds) within which a recently revoked refresh token is treated
# as a benign concurrent multi-tab refresh rather than token theft.
REUSE_GRACE_SECONDS = 15


def is_concurrent_reuse(revoked_at: datetime | None, now: datetime,
                        grace_seconds: int = REUSE_GRACE_SECONDS) -> bool:
    """Return True if the token was revoked within grace_seconds (reject without revoking all sessions)."""
    if revoked_at is None:
        return False
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed = (now - revoked_at).total_seconds()
    return 0 <= elapsed <= grace_seconds
