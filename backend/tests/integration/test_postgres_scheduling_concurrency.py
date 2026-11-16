"""Prueba real de EXCLUDE constraints R4.2 con transacciones concurrentes.
Requiere TEST_DATABASE_URL migrada y rol runtime sin SUPERUSER/BYPASSRLS.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Definir TEST_DATABASE_URL para concurrencia PostgreSQL real")


def _race_same_asset(engine, asset_kind: str):
    tenant_id = None
    slug = f"r42-{asset_kind}-{uuid4().hex}"
    try:
        with engine.begin() as conn:
            role = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
            assert role.rolsuper is False and role.rolbypassrls is False
            tenant_id = conn.execute(text("SELECT nextval(pg_get_serial_sequence('tenants','id'))")).scalar_one()
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
            conn.execute(text("INSERT INTO tenants(id,name,slug) VALUES (:id,'R42 test',:slug)"), {"id": tenant_id, "slug": slug})
            branch_id = conn.execute(text("INSERT INTO branches(tenant_id,name,timezone) VALUES (:t,'Concurrency','America/Santiago') RETURNING id"), {"t": tenant_id}).scalar_one()
            customer_id = conn.execute(text("INSERT INTO customers(tenant_id,name,phone) VALUES (:t,'Customer',:phone) RETURNING id"), {"t": tenant_id, "phone": f"+569{tenant_id:08d}"}).scalar_one()
            service_id = conn.execute(text("INSERT INTO services(tenant_id,name,duration_minutes,buffer_minutes,price) VALUES (:t,'Cut',30,10,10000) RETURNING id"), {"t": tenant_id}).scalar_one()
            asset_id = conn.execute(text(
                "INSERT INTO staff(tenant_id,branch_id,name) VALUES (:t,:b,'Stylist') RETURNING id" if asset_kind == "staff"
                else "INSERT INTO resources(tenant_id,branch_id,resource_type,name) VALUES (:t,:b,'CHAIR','Chair 1') RETURNING id"
            ), {"t": tenant_id, "b": branch_id}).scalar_one()

        barrier = Barrier(2)
        column = "staff_id" if asset_kind == "staff" else "resource_id"

        def attempt(_):
            try:
                with engine.begin() as conn:
                    conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
                    barrier.wait(timeout=10)
                    conn.execute(text(f"""INSERT INTO appointments
                        (tenant_id,branch_id,customer_id,service_id,{column},starts_at,ends_at,status)
                        VALUES (:t,:b,:c,:s,:asset,'2030-05-06 14:00:00+00','2030-05-06 14:40:00+00','CONFIRMED')"""),
                        {"t": tenant_id, "b": branch_id, "c": customer_id, "s": service_id, "asset": asset_id})
                return "created"
            except IntegrityError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [0, 1]))
        assert sorted(results) == ["conflict", "created"]
        # Los intervalos semiabiertos [inicio, fin) permiten una reserva que
        # comienza exactamente cuando termina la anterior.
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
            conn.execute(text(f"""INSERT INTO appointments
                (tenant_id,branch_id,customer_id,service_id,{column},starts_at,ends_at,status)
                SELECT :t, a.branch_id, a.customer_id, a.service_id, :asset,
                       '2030-05-06 14:40:00+00','2030-05-06 15:20:00+00','CONFIRMED'
                  FROM appointments a WHERE a.tenant_id=:t AND a.{column}=:asset LIMIT 1"""),
                {"t": tenant_id, "asset": asset_id})
            count = conn.execute(text(f"SELECT count(*) FROM appointments WHERE tenant_id=:t AND {column}=:asset"),
                                 {"t": tenant_id, "asset": asset_id}).scalar_one()
            assert count == 2
    finally:
        if tenant_id is not None:
            with engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
                conn.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": tenant_id})


def test_two_concurrent_bookings_cannot_overlap_same_staff():
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=2, pool_pre_ping=True)
    try:
        _race_same_asset(engine, "staff")
    finally:
        engine.dispose()


def test_two_concurrent_bookings_cannot_overlap_same_resource():
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=2, pool_pre_ping=True)
    try:
        _race_same_asset(engine, "resource")
    finally:
        engine.dispose()
