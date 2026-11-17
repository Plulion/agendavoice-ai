"""R4.2: weekly schedules, breaks, availability, cancellation, and GiST exclusion constraints."""
from alembic import op
import sqlalchemy as sa

revision = "0003_r42_universal_scheduling"
down_revision = "0002_r41_security_core"
branch_labels = None
depends_on = None

TENANT_SCHEDULE_TABLES = (
    "branch_hours", "branch_breaks", "staff_hours", "staff_breaks",
    "resource_hours", "resource_breaks",
)


def _preflight(bind):
    invalid_status = bind.execute(sa.text(
        "SELECT id, status FROM appointments WHERE status NOT IN ('PENDING','CONFIRMED','CANCELLED','COMPLETED','NO_SHOW') LIMIT 1"
    )).first()
    if invalid_status:
        raise RuntimeError(f"R4.2: reserva {invalid_status.id} tiene estado no reconocido ({invalid_status.status})")
    invalid_timezone = bind.execute(sa.text(
        "SELECT b.id, b.timezone FROM branches b WHERE NOT EXISTS (SELECT 1 FROM pg_timezone_names z WHERE z.name=b.timezone) LIMIT 1"
    )).first()
    if invalid_timezone:
        raise RuntimeError(f"R4.2: sucursal {invalid_timezone.id} tiene zona horaria no reconocida ({invalid_timezone.timezone})")
    invalid_service = bind.execute(sa.text(
        "SELECT id FROM services WHERE duration_minutes NOT BETWEEN 1 AND 600 OR buffer_minutes NOT BETWEEN 0 AND 180 LIMIT 1"
    )).first()
    if invalid_service:
        raise RuntimeError(f"R4.2: servicio {invalid_service.id} tiene duración/buffer fuera de rango")
    staff_overlap = bind.execute(sa.text("""
        SELECT a.id, b.id FROM appointments a JOIN appointments b
          ON a.id < b.id AND a.tenant_id=b.tenant_id AND a.staff_id=b.staff_id
         AND a.staff_id IS NOT NULL AND a.status IN ('PENDING','CONFIRMED')
         AND b.status IN ('PENDING','CONFIRMED')
         AND tstzrange(a.starts_at,a.ends_at,'[)') && tstzrange(b.starts_at,b.ends_at,'[)')
        LIMIT 1
    """)).first()
    if staff_overlap:
        raise RuntimeError(f"R4.2: existen reservas solapadas para profesional (ids {staff_overlap[0]}, {staff_overlap[1]}). Corrige antes de migrar")
    resource_overlap = bind.execute(sa.text("""
        SELECT a.id, b.id FROM appointments a JOIN appointments b
          ON a.id < b.id AND a.tenant_id=b.tenant_id AND a.resource_id=b.resource_id
         AND a.resource_id IS NOT NULL AND a.status IN ('PENDING','CONFIRMED')
         AND b.status IN ('PENDING','CONFIRMED')
         AND tstzrange(a.starts_at,a.ends_at,'[)') && tstzrange(b.starts_at,b.ends_at,'[)')
        LIMIT 1
    """)).first()
    if resource_overlap:
        raise RuntimeError(f"R4.2: existen reservas solapadas para recurso (ids {resource_overlap[0]}, {resource_overlap[1]}). Corrige antes de migrar")
    staff_branch_mismatch = bind.execute(sa.text("""
        SELECT a.id FROM appointments a JOIN staff st ON st.id=a.staff_id
        WHERE a.staff_id IS NOT NULL AND (a.tenant_id <> st.tenant_id OR a.branch_id <> st.branch_id) LIMIT 1
    """)).first()
    if staff_branch_mismatch:
        raise RuntimeError(f"R4.2: la reserva {staff_branch_mismatch.id} asigna un profesional de otra sucursal")
    resource_branch_mismatch = bind.execute(sa.text("""
        SELECT a.id FROM appointments a JOIN resources r ON r.id=a.resource_id
        WHERE a.resource_id IS NOT NULL AND (a.tenant_id <> r.tenant_id OR a.branch_id <> r.branch_id) LIMIT 1
    """)).first()
    if resource_branch_mismatch:
        raise RuntimeError(f"R4.2: la reserva {resource_branch_mismatch.id} asigna un recurso de otra sucursal")


def _schedule_index(name, entity_columns):
    if "staff_id" in entity_columns:
        return f"ix_{name}_tenant_branch_staff_day", ["tenant_id", "branch_id", "staff_id", "weekday"]
    if "resource_id" in entity_columns:
        return f"ix_{name}_tenant_branch_resource_day", ["tenant_id", "branch_id", "resource_id", "weekday"]
    return f"ix_{name}_tenant_branch_day", ["tenant_id", "branch_id", "weekday"]


def _create_schedule_table(name, entity_columns, unique_columns, checks, foreign_keys):
    columns = [sa.Column("id", sa.Integer(), primary_key=True),
               sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
               sa.Column("branch_id", sa.Integer(), nullable=False)]
    for column in entity_columns:
        columns.append(sa.Column(column, sa.Integer(), nullable=False))
    columns.extend([
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.Time()),
        sa.Column("closes_at", sa.Time()),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
    ])
    constraints = [sa.UniqueConstraint(*unique_columns, name=f"uq_{name}_weekday"),
                   sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=f"ck_{name}_weekday"),
                   sa.CheckConstraint("(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR (NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)", name=f"ck_{name}_range")]
    for fk_name, local_cols, target, remote_cols in foreign_keys:
        constraints.append(sa.ForeignKeyConstraint(local_cols, [f"{target}.{c}" for c in remote_cols], ondelete="CASCADE", name=fk_name))
    op.create_table(name, *columns, *constraints)
    index_name, index_columns = _schedule_index(name, entity_columns)
    op.create_index(index_name, name, index_columns)


def _create_break_table(name, entity_columns, foreign_keys):
    columns = [sa.Column("id", sa.Integer(), primary_key=True),
               sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
               sa.Column("branch_id", sa.Integer(), nullable=False)]
    for column in entity_columns:
        columns.append(sa.Column(column, sa.Integer(), nullable=False))
    columns.extend([sa.Column("weekday", sa.Integer(), nullable=False),
                    sa.Column("starts_at", sa.Time(), nullable=False),
                    sa.Column("ends_at", sa.Time(), nullable=False)])
    constraints = [sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=f"ck_{name}_weekday"),
                   sa.CheckConstraint("ends_at > starts_at", name=f"ck_{name}_range")]
    for fk_name, local_cols, target, remote_cols in foreign_keys:
        constraints.append(sa.ForeignKeyConstraint(local_cols, [f"{target}.{c}" for c in remote_cols], ondelete="CASCADE", name=fk_name))
    op.create_table(name, *columns, *constraints)
    index_name, index_columns = _schedule_index(name, entity_columns)
    op.create_index(index_name, name, index_columns)


def upgrade():
    bind = op.get_bind()

    # btree_gist enables combining scalar equality (tenant_id, staff_id/resource_id) with tstzrange overlap.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # Temporarily disable RLS inside this DDL migration transaction to run preflight checks.
    op.execute("ALTER TABLE appointments DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE services DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resources DISABLE ROW LEVEL SECURITY")
    _preflight(bind)
    op.execute("ALTER TABLE staff ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resources FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE services ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE services FORCE ROW LEVEL SECURITY")
    op.add_column("appointments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("cancellation_reason", sa.String(500), nullable=True))
    op.create_check_constraint("ck_appointment_status", "appointments",
        "status IN ('PENDING','CONFIRMED','CANCELLED','COMPLETED','NO_SHOW')")
    op.create_check_constraint("ck_service_duration_range", "services",
        "duration_minutes BETWEEN 1 AND 600 AND buffer_minutes BETWEEN 0 AND 180")

    # Include branch_id in composite unique and foreign keys for staff and resources.
    op.create_unique_constraint("uq_staff_tenant_branch_id", "staff", ["tenant_id", "branch_id", "id"])
    op.create_unique_constraint("uq_resources_tenant_branch_id", "resources", ["tenant_id", "branch_id", "id"])
    op.drop_constraint("fk_appointment_tenant_staff", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointment_tenant_resource", "appointments", type_="foreignkey")
    op.create_foreign_key("fk_appointment_tenant_branch_staff", "appointments", "staff",
        ["tenant_id", "branch_id", "staff_id"], ["tenant_id", "branch_id", "id"])
    op.create_foreign_key("fk_appointment_tenant_branch_resource", "appointments", "resources",
        ["tenant_id", "branch_id", "resource_id"], ["tenant_id", "branch_id", "id"])

    _create_schedule_table("branch_hours", [], ["tenant_id", "branch_id", "weekday"], [], [
        ("fk_branch_hours_branch", ["tenant_id", "branch_id"], "branches", ["tenant_id", "id"])])
    _create_break_table("branch_breaks", [], [
        ("fk_branch_breaks_branch", ["tenant_id", "branch_id"], "branches", ["tenant_id", "id"])])
    _create_schedule_table("staff_hours", ["staff_id"], ["tenant_id", "staff_id", "weekday"], [], [
        ("fk_staff_hours_tenant_branch_staff", ["tenant_id", "branch_id", "staff_id"], "staff", ["tenant_id", "branch_id", "id"])])
    _create_break_table("staff_breaks", ["staff_id"], [
        ("fk_staff_breaks_tenant_branch_staff", ["tenant_id", "branch_id", "staff_id"], "staff", ["tenant_id", "branch_id", "id"])])
    _create_schedule_table("resource_hours", ["resource_id"], ["tenant_id", "resource_id", "weekday"], [], [
        ("fk_resource_hours_tenant_branch_resource", ["tenant_id", "branch_id", "resource_id"], "resources", ["tenant_id", "branch_id", "id"])])
    _create_break_table("resource_breaks", ["resource_id"], [
        ("fk_resource_breaks_tenant_branch_resource", ["tenant_id", "branch_id", "resource_id"], "resources", ["tenant_id", "branch_id", "id"])])

    for table in TENANT_SCHEDULE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")

    # Physical database-level exclusion constraints preventing overlapping active appointments.
    op.execute("""ALTER TABLE appointments ADD CONSTRAINT ex_appointments_staff_no_overlap
        EXCLUDE USING gist (tenant_id WITH =, staff_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&)
        WHERE (staff_id IS NOT NULL AND status IN ('PENDING','CONFIRMED'))""")
    op.execute("""ALTER TABLE appointments ADD CONSTRAINT ex_appointments_resource_no_overlap
        EXCLUDE USING gist (tenant_id WITH =, resource_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&)
        WHERE (resource_id IS NOT NULL AND status IN ('PENDING','CONFIRMED'))""")


def downgrade():
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_resource_no_overlap")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_staff_no_overlap")
    for table in reversed(TENANT_SCHEDULE_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
    op.drop_constraint("ck_service_duration_range", "services", type_="check")
    op.drop_constraint("ck_appointment_status", "appointments", type_="check")
    op.drop_column("appointments", "cancellation_reason")
    op.drop_column("appointments", "cancelled_at")
    op.drop_constraint("fk_appointment_tenant_branch_staff", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointment_tenant_branch_resource", "appointments", type_="foreignkey")
    op.create_foreign_key("fk_appointment_tenant_staff", "appointments", "staff", ["tenant_id", "staff_id"], ["tenant_id", "id"])
    op.create_foreign_key("fk_appointment_tenant_resource", "appointments", "resources", ["tenant_id", "resource_id"], ["tenant_id", "id"])
    op.drop_constraint("uq_staff_tenant_branch_id", "staff", type_="unique")
    op.drop_constraint("uq_resources_tenant_branch_id", "resources", type_="unique")
