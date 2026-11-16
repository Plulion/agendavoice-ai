"""Política DST R4.2.1 (horas ambiguas y nuevas) y limitador de intentos.

Solo usa la biblioteca estándar y módulos sin dependencias externas, por lo que
se puede ejecutar también fuera de Docker.
"""
from datetime import date, time, timezone
from app.modules.scheduling.availability import local_slot_to_utc, is_ambiguous_local
from app.core.rate_limiter import FixedWindowLimiter

TZ = "America/Santiago"


def test_ambiguous_hour_is_rejected_not_silently_resolved():
    # 4 abr 2026: a las 24:00 Santiago atrasa a 23:00; 23:30 ocurre dos veces.
    assert is_ambiguous_local(date(2026, 4, 4), time(23, 30), TZ) is True
    assert local_slot_to_utc(date(2026, 4, 4), time(23, 30), TZ) is None


def test_nonexistent_hour_is_rejected():
    # 6 sep 2026: la hora 00:xx no existe (adelanto a 01:00).
    assert is_ambiguous_local(date(2026, 9, 6), time(0, 30), TZ) is False
    assert local_slot_to_utc(date(2026, 9, 6), time(0, 30), TZ) is None


def test_unambiguous_hour_converts_once_to_utc():
    # Mayo 2026 (invierno, UTC-4): 10:00 local = 14:00 UTC.
    result = local_slot_to_utc(date(2026, 5, 10), time(10, 0), TZ)
    assert result is not None
    assert result.astimezone(timezone.utc).hour == 14
    assert is_ambiguous_local(date(2026, 5, 10), time(10, 0), TZ) is False


def test_limiter_blocks_after_limit_and_resets_next_window():
    now = [1000.0]
    limiter = FixedWindowLimiter(redis_client=None, clock=lambda: now[0])
    assert [limiter.hit("k", 3, 60) for _ in range(3)] == [True, True, True]
    assert limiter.hit("k", 3, 60) is False
    now[0] += 60  # nueva ventana
    assert limiter.hit("k", 3, 60) is True


def test_limiter_falls_back_to_memory_when_redis_fails():
    class BrokenRedis:
        def pipeline(self):
            raise ConnectionError("redis caído")

    limiter = FixedWindowLimiter(redis_client=BrokenRedis(), clock=lambda: 0.0)
    assert [limiter.hit("x", 2, 60) for _ in range(3)] == [True, True, False]


def test_limiter_keys_are_independent():
    limiter = FixedWindowLimiter(redis_client=None, clock=lambda: 0.0)
    assert limiter.hit("ip-a", 1, 60) is True
    assert limiter.hit("ip-b", 1, 60) is True
    assert limiter.hit("ip-a", 1, 60) is False


def test_audit_logs_are_append_only_in_migrations():
    from pathlib import Path
    text = (Path(__file__).parents[1] / "alembic" / "versions" / "0004_r421_audit_append_only.py").read_text()
    assert "REVOKE UPDATE, DELETE ON audit_logs FROM agendavoice_app" in text


if __name__ == "__main__":
    import sys
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as exc:
                failures += 1
                print("FAIL", name, exc)
    sys.exit(1 if failures else 0)
