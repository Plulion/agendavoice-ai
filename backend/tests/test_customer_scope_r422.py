"""Pruebas de la regla de clientes por sucursal y de la ventana de reuso de refresh (R4.2.2).

Solo biblioteca estándar. Las pruebas de PostgreSQL están en tests/integration.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.modules.customers.visibility import customer_visible
from app.core.session_rules import is_concurrent_reuse


def test_admin_sees_every_customer():
    assert customer_visible(None, None, []) is True
    assert customer_visible(None, 9, [7]) is True


def test_restricted_user_sees_customer_from_home_branch():
    assert customer_visible([1], 1, []) is True


def test_restricted_user_sees_customer_visited_in_own_branch():
    assert customer_visible([1], None, [2, 1]) is True


def test_restricted_user_does_not_see_other_branch_customer():
    assert customer_visible([1], 2, [2]) is False
    assert customer_visible([1], None, [2]) is False


def test_user_without_branches_sees_nothing():
    assert customer_visible([], 1, [1]) is False


def test_reuse_inside_grace_is_concurrent_not_theft():
    now = datetime(2026, 11, 16, 12, 0, 10, tzinfo=timezone.utc)
    revoked = now - timedelta(seconds=5)
    assert is_concurrent_reuse(revoked, now) is True


def test_reuse_after_grace_is_theft_signal():
    now = datetime(2026, 11, 16, 12, 0, 40, tzinfo=timezone.utc)
    revoked = now - timedelta(seconds=30)
    assert is_concurrent_reuse(revoked, now) is False


def test_reuse_of_never_revoked_token_is_not_concurrent():
    assert is_concurrent_reuse(None, datetime.now(timezone.utc)) is False


def test_naive_datetimes_are_treated_as_utc():
    now = datetime(2026, 11, 16, 12, 0, 10)
    revoked = datetime(2026, 11, 16, 12, 0, 8)
    assert is_concurrent_reuse(revoked, now) is True


def test_migration_0005_backfills_with_rls_disabled_and_restores_force():
    text = (Path(__file__).parents[1] / "alembic" / "versions" / "0005_r422_customer_home_branch.py").read_text()
    assert "home_branch_id" in text
    assert text.index("DISABLE ROW LEVEL SECURITY") < text.index("UPDATE customers")
    assert text.count("FORCE ROW LEVEL SECURITY") >= 2


def test_api_enforces_customer_scope_in_appointments_and_customers():
    text = (Path(__file__).parents[1] / "app" / "main.py").read_text()
    assert "_customer_scope(" in text
    assert "_customer_visible(db, user, customer)" in text


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
