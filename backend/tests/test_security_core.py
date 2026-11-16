from pathlib import Path
from datetime import datetime
import pytest
from app.schemas import RegisterIn, BranchIn, ServiceIn, AppointmentIn, UserCreateIn
from app.core.roles import ROLE_HIERARCHY


def test_registration_password_minimum():
    with pytest.raises(Exception):
        RegisterIn(company_name="Salón Demo", admin_name="Admin", email="admin@example.com", password="short")


def test_branch_timezone_default():
    assert BranchIn(name="Sucursal Centro").timezone == "America/Santiago"


def test_service_duration_must_be_positive():
    with pytest.raises(Exception):
        ServiceIn(name="Corte", duration_minutes=0, price=10000)


def test_appointment_requires_timezone_and_assigned_resource():
    with pytest.raises(Exception):
        AppointmentIn(branch_id=1, customer_id=1, service_id=1,
                      starts_at=datetime(2027, 1, 1, 10, 0))
    with pytest.raises(Exception):
        AppointmentIn(branch_id=1, customer_id=1, service_id=1,
                      starts_at="2027-01-01T10:00:00-03:00")


def test_appointment_normalizes_timezone_to_utc():
    item = AppointmentIn(branch_id=1, customer_id=1, service_id=1, staff_id=1,
                         starts_at="2027-01-01T10:00:00-03:00")
    assert item.starts_at.isoformat() == "2027-01-01T13:00:00+00:00"


def test_user_creation_requires_branch_scope():
    item = UserCreateIn(name="Operador", email="op@example.com", password="long-password-123",
                        role="OPERATOR", branch_ids=[1, 1, 2])
    assert item.branch_ids == [1, 1, 2]
    with pytest.raises(Exception):
        UserCreateIn(name="Operador", email="op@example.com", password="long-password-123",
                     role="OPERATOR", branch_ids=[])


def test_role_catalog_matches_architecture():
    assert set(ROLE_HIERARCHY) == {"SUPER_ADMIN", "TENANT_ADMIN", "BRANCH_MANAGER", "OPERATOR", "READ_ONLY"}
    assert ROLE_HIERARCHY["TENANT_ADMIN"] > ROLE_HIERARCHY["BRANCH_MANAGER"] > ROLE_HIERARCHY["OPERATOR"] > ROLE_HIERARCHY["READ_ONLY"]


def test_migrations_enforce_rls_without_login_bypass():
    root = Path(__file__).parents[1] / "alembic" / "versions"
    initial = (root / "0001_initial.py").read_text()
    r41 = (root / "0002_r41_security_core.py").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in initial
    assert "FORCE ROW LEVEL SECURITY" in initial
    assert "app.tenant_id" in initial
    assert "app.auth_lookup" in initial
    upgrade = r41.split("def downgrade():")[0]
    assert "app.auth_lookup" not in upgrade
    assert "DROP POLICY IF EXISTS tenant_isolation ON users" in r41
    assert "refresh_sessions" in r41 and "user_branch_access" in r41
    assert "DISABLE ROW LEVEL SECURITY" in r41 and "BACKFILL_TABLES" in r41
    assert "ENABLE ROW LEVEL SECURITY" in r41 and "FORCE ROW LEVEL SECURITY" in r41
    assert "auth_identities" in r41 and "ForeignKeyConstraint" in r41
    assert "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY" in r41
    assert "ALTER TABLE tenants FORCE ROW LEVEL SECURITY" in r41
    assert "uq_branches_tenant_id" in r41 and "uq_users_tenant_id" in r41
    assert "fk_appointment_tenant_" in r41 and "fk_audit_tenant_actor" in r41
    assert "_preflight(op.get_bind())" in r41


def test_production_rejects_placeholder_jwt_secret():
    from app.core.config import Settings
    with pytest.raises(Exception):
        Settings(app_env="production", jwt_secret="CHANGE_ME_this_is_a_placeholder_secret")
    Settings(app_env="production", jwt_secret="a-real-random-secret-value-should-be-set")


def test_tenant_context_is_reapplied_for_each_transaction():
    source = (Path(__file__).parents[1] / "app" / "core" / "db.py").read_text()
    assert 'listens_for(Session, "after_begin")' in source
    assert "session.info.get(\"tenant_id\")" in source
    assert "set_config('app.tenant_id', :value, true)" in source


def test_tenant_context_listener_reapplies_after_commit(tmp_path, monkeypatch):
    import importlib
    import sys
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import Session, sessionmaker
    from app.core.config import settings
    from app.core.tenant_context import set_tenant_context

    existing_module = sys.modules.get("app.core.db")
    owns_listener = existing_module is None
    original_url = settings.database_url
    if owns_listener:
        monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'tenant-context.db'}")
        db_module = importlib.import_module("app.core.db")
        engine = db_module.engine
        SessionFactory = db_module.SessionLocal
        listener = db_module._apply_transaction_context
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'tenant-context.db'}")
        SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        listener = None

    calls = []
    @event.listens_for(engine, "connect")
    def sqlite_set_config(dbapi_connection, connection_record):
        dbapi_connection.create_function("set_config", 3,
            lambda name, value, local: calls.append((name, value, local)) or value)

    session = SessionFactory()
    try:
        set_tenant_context(session, 42)
        session.commit()
        session.execute(text("SELECT 1")).scalar_one()
        assert session.info["tenant_id"] == 42
        assert len(calls) >= 3  # after_begin, set explícito y after_begin post-COMMIT
        assert all(call[0] == "app.tenant_id" and call[1] == "42" and bool(call[2]) for call in calls)
    finally:
        session.close()
        engine.dispose()
        if owns_listener:
            event.remove(Session, "after_begin", listener)
            sys.modules.pop("app.core.db", None)
            settings.database_url = original_url


def test_r42_migration_adds_rls_schedules_and_database_overlap_constraints():
    root = Path(__file__).parents[1] / "alembic" / "versions"
    r42 = (root / "0003_r42_universal_scheduling.py").read_text()
    assert "down_revision = \"0002_r41_security_core\"" in r42
    for table in ("branch_hours", "branch_breaks", "staff_hours", "staff_breaks", "resource_hours", "resource_breaks"):
        assert f'"{table}"' in r42
    assert "ENABLE ROW LEVEL SECURITY" in r42
    assert "FORCE ROW LEVEL SECURITY" in r42
    assert "CREATE POLICY tenant_isolation" in r42
    assert "ex_appointments_staff_no_overlap" in r42
    assert "ex_appointments_resource_no_overlap" in r42
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in r42
    assert "pg_timezone_names" in r42
    assert "uq_staff_tenant_branch_id" in r42
    assert "fk_appointment_tenant_branch_staff" in r42
    assert "fk_appointment_tenant_branch_resource" in r42
