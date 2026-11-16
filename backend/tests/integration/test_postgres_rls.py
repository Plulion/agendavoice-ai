"""Prueba real RLS. Requiere TEST_DATABASE_URL con migraciones Alembic aplicadas."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.tenant_context import set_tenant_context

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Definir TEST_DATABASE_URL para ejecutar RLS real")


def test_rls_isolates_tenants_and_transaction_context_does_not_leak():
    # Importa el módulo que registra el listener Session.after_begin usado por la API.
    import app.core.db  # noqa: F401
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    tenant_a = tenant_b = None
    try:
        with engine.connect() as conn:
            role = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
            assert role.rolsuper is False and role.rolbypassrls is False, "TEST_DATABASE_URL debe usar un rol runtime sin SUPERUSER/BYPASSRLS"
            table_security = conn.execute(text("SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner) = current_user AS is_owner FROM pg_class c WHERE c.relname IN ('branches', 'tenants', 'branch_hours', 'branch_breaks', 'staff_hours', 'staff_breaks', 'resource_hours', 'resource_breaks') ORDER BY c.relname")).all()
            assert len(table_security) == 8
            assert all(row.relrowsecurity and row.relforcerowsecurity for row in table_security)
            assert all(row.is_owner is False for row in table_security), "El rol runtime no debe ser propietario de tablas protegidas"

        with engine.begin() as conn:
            tenant_a = conn.execute(text("SELECT nextval(pg_get_serial_sequence('tenants', 'id'))")).scalar_one()
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_a)})
            conn.execute(text("INSERT INTO tenants(id, name, slug) VALUES (:tid, 'RLS A', 'rls-a-' || gen_random_uuid())"), {"tid": tenant_a})
            branch_a = conn.execute(text("INSERT INTO branches(tenant_id, name, timezone) VALUES (:tid, 'A branch', 'America/Santiago') RETURNING id"), {"tid": tenant_a}).scalar_one()
            branch_a_other = conn.execute(text("INSERT INTO branches(tenant_id, name, timezone) VALUES (:tid, 'A branch 2', 'America/Santiago') RETURNING id"), {"tid": tenant_a}).scalar_one()
            customer_a = conn.execute(text("INSERT INTO customers(tenant_id, name, phone) VALUES (:tid, 'Customer A', '+56900000001') RETURNING id"), {"tid": tenant_a}).scalar_one()
            staff_a_other = conn.execute(text("INSERT INTO staff(tenant_id,branch_id,name) VALUES (:tid,:branch,'Other branch staff') RETURNING id"), {"tid": tenant_a, "branch": branch_a_other}).scalar_one()
            service_a = conn.execute(text("INSERT INTO services(tenant_id, name, duration_minutes, price) VALUES (:tid, 'Service A', 30, 10000) RETURNING id"), {"tid": tenant_a}).scalar_one()
            conn.execute(text("INSERT INTO branch_hours(tenant_id,branch_id,weekday,opens_at,closes_at,is_closed) VALUES (:tid,:branch,0,'09:00','17:00',false)"), {"tid": tenant_a, "branch": branch_a})
            tenant_b = conn.execute(text("SELECT nextval(pg_get_serial_sequence('tenants', 'id'))")).scalar_one()
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_b)})
            conn.execute(text("INSERT INTO tenants(id, name, slug) VALUES (:tid, 'RLS B', 'rls-b-' || gen_random_uuid())"), {"tid": tenant_b})
            branch_b = conn.execute(text("INSERT INTO branches(tenant_id, name, timezone) VALUES (:tid, 'B branch', 'America/Santiago') RETURNING id"), {"tid": tenant_b}).scalar_one()
            customer_b = conn.execute(text("INSERT INTO customers(tenant_id, name, phone) VALUES (:tid, 'Customer B', '+56911111111') RETURNING id"), {"tid": tenant_b}).scalar_one()
            conn.execute(text("INSERT INTO branch_hours(tenant_id,branch_id,weekday,opens_at,closes_at,is_closed) VALUES (:tid,:branch,0,'10:00','18:00',false)"), {"tid": tenant_b, "branch": branch_b})

        # Sin contexto no hay filas visibles.
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM tenants WHERE id IN (:a, :b)"), {"a": tenant_a, "b": tenant_b}).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM branches WHERE name IN ('A branch','B branch')")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM branch_hours")).scalar_one() == 0

        # El tenant A solo ve su propia fila y el contexto se reaplica tras COMMIT.
        db = Session()
        set_tenant_context(db, tenant_a)
        assert db.execute(text("SELECT name FROM tenants WHERE id IN (:a, :b)"), {"a": tenant_a, "b": tenant_b}).scalars().all() == ["RLS A"]
        assert db.execute(text("SELECT name FROM branches WHERE name IN ('A branch','B branch')")).scalars().all() == ["A branch"]
        assert db.execute(text("SELECT count(*) FROM branch_hours")).scalar_one() == 1
        db.commit()
        assert db.execute(text("SELECT name FROM branches WHERE name IN ('A branch','B branch')")).scalars().all() == ["A branch"]
        assert db.execute(text("SELECT count(*) FROM branch_hours")).scalar_one() == 1
        db.close()

        # La sucursal forma parte de la FK compuesta: mismo tenant, otra sucursal no vale.
        db = Session()
        set_tenant_context(db, tenant_a)
        with pytest.raises(Exception):
            db.execute(text("INSERT INTO staff_hours(tenant_id,branch_id,staff_id,weekday,opens_at,closes_at,is_closed) VALUES (:t,:branch,:staff,0,'09:00','17:00',false)"),
                       {"t": tenant_a, "branch": branch_a, "staff": staff_a_other})
        db.rollback()
        db.close()

        db = Session()
        set_tenant_context(db, tenant_a)
        with pytest.raises(Exception):
            db.execute(text("INSERT INTO appointments(tenant_id,branch_id,customer_id,service_id,staff_id,starts_at,ends_at,status) VALUES (:t,:branch,:customer,:service,:staff,now()+interval '1 day',now()+interval '1 day 30 minutes','CONFIRMED')"),
                       {"t": tenant_a, "branch": branch_a, "customer": customer_a, "service": service_a, "staff": staff_a_other})
        db.rollback()
        db.close()

        # WITH CHECK impide tenant_id ajeno.
        db = Session()
        set_tenant_context(db, tenant_a)
        with pytest.raises(Exception):
            db.execute(text("INSERT INTO branches(tenant_id, name, timezone) VALUES (:tid, 'cross tenant', 'America/Santiago')"), {"tid": tenant_b})
        db.rollback()
        db.close()

        db = Session()
        set_tenant_context(db, tenant_a)
        with pytest.raises(Exception):
            db.execute(text("INSERT INTO staff(tenant_id, branch_id, name) VALUES (:tenant, :branch, 'Wrong branch')"),
                       {"tenant": tenant_a, "branch": branch_b})
        db.rollback()
        db.close()

        db = Session()
        set_tenant_context(db, tenant_a)
        with pytest.raises(Exception):
            db.execute(text("""INSERT INTO appointments(tenant_id, branch_id, customer_id, service_id,
                starts_at, ends_at, status) VALUES (:tenant, :branch, :customer, :service,
                now() + interval '1 day', now() + interval '1 day 30 minutes', 'CONFIRMED')"""),
                {"tenant": tenant_a, "branch": branch_a, "customer": customer_b, "service": service_a})
        db.rollback()
        db.close()
    finally:
        # Limpieza explícita bajo el contexto de cada tenant.
        if tenant_a is not None:
            with engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_a)})
                conn.execute(text("DELETE FROM branches WHERE tenant_id = :tid"), {"tid": tenant_a})
                conn.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_a})
        if tenant_b is not None:
            with engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_b)})
                conn.execute(text("DELETE FROM branches WHERE tenant_id = :tid"), {"tid": tenant_b})
                conn.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_b})
        engine.dispose()
