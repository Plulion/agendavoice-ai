"""R4.1: identidad, sesiones rotativas, roles, RLS y relaciones tenant-safe."""
from alembic import op
import sqlalchemy as sa

revision = "0002_r41_security_core"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

BACKFILL_TABLES = ("users", "branches", "customers", "services", "staff", "resources", "appointments", "audit_logs")
TENANT_TABLES = ("refresh_sessions", "user_branch_access")


def _preflight(bind):
    duplicate_email = bind.execute(sa.text(
        "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicate_email:
        raise RuntimeError("R4.1: existen correos que colisionan al normalizar a minúsculas; corrígelos antes de migrar")

    checks = {
        "staff": "SELECT 1 FROM staff s JOIN branches b ON b.id=s.branch_id WHERE s.tenant_id <> b.tenant_id LIMIT 1",
        "resources": "SELECT 1 FROM resources r JOIN branches b ON b.id=r.branch_id WHERE r.tenant_id <> b.tenant_id LIMIT 1",
        "appointments": """SELECT 1 FROM appointments a
            LEFT JOIN branches b ON b.id=a.branch_id
            LEFT JOIN customers c ON c.id=a.customer_id
            LEFT JOIN services s ON s.id=a.service_id
            LEFT JOIN staff st ON st.id=a.staff_id
            LEFT JOIN resources r ON r.id=a.resource_id
            WHERE b.tenant_id <> a.tenant_id OR c.tenant_id <> a.tenant_id
               OR s.tenant_id <> a.tenant_id
               OR (a.staff_id IS NOT NULL AND st.tenant_id <> a.tenant_id)
               OR (a.resource_id IS NOT NULL AND r.tenant_id <> a.tenant_id)
            LIMIT 1""",
        "audit_logs": """SELECT 1 FROM audit_logs a JOIN users u ON u.id=a.actor_user_id
            WHERE a.actor_user_id IS NOT NULL AND u.tenant_id <> a.tenant_id LIMIT 1""",
    }
    for table, query in checks.items():
        if bind.execute(sa.text(query)).first():
            raise RuntimeError(f"R4.1: se detectaron referencias entre tenants en {table}; corrígelas antes de migrar")


def upgrade():
    # El tenant raíz queda bajo RLS. En registro, la API reserva primero el ID
    # de secuencia, establece el GUC y luego inserta la fila con ese ID.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON tenants USING (id = NULLIF(current_setting('app.tenant_id', true), '')::integer) WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")

    # R4.0 tenía FORCE RLS en las tablas de tenant. Se desactiva solo dentro de
    # esta transacción de migración para verificar/backfill de datos existentes.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    for table in BACKFILL_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    _preflight(op.get_bind())

    # Correo normalizado y unicidad global del índice de identidad.
    op.execute("UPDATE users SET email = lower(email)")
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"])
    op.create_check_constraint("ck_users_role", "users", "role IN ('SUPER_ADMIN', 'TENANT_ADMIN', 'BRANCH_MANAGER', 'OPERATOR', 'READ_ONLY')")

    # Claves compuestas: una relación nunca puede apuntar a una fila de otro tenant.
    op.create_unique_constraint("uq_users_tenant_id", "users", ["tenant_id", "id"])
    op.create_unique_constraint("uq_branches_tenant_id", "branches", ["tenant_id", "id"])
    op.create_unique_constraint("uq_customers_tenant_id", "customers", ["tenant_id", "id"])
    op.create_unique_constraint("uq_services_tenant_id", "services", ["tenant_id", "id"])
    op.create_unique_constraint("uq_staff_tenant_id", "staff", ["tenant_id", "id"])
    op.create_unique_constraint("uq_resources_tenant_id", "resources", ["tenant_id", "id"])

    op.create_table("auth_identities",
        sa.Column("email", sa.String(255), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"], ondelete="CASCADE"))
    op.create_index("ix_auth_identities_tenant_id", "auth_identities", ["tenant_id"])
    op.execute("INSERT INTO auth_identities (email, user_id, tenant_id) SELECT lower(email), id, tenant_id FROM users")

    # Reemplaza FKs simples por FKs compuestas tenant-safe.
    op.drop_constraint("staff_branch_id_fkey", "staff", type_="foreignkey")
    op.create_foreign_key("fk_staff_tenant_branch", "staff", "branches",
        ["tenant_id", "branch_id"], ["tenant_id", "id"], ondelete="CASCADE")
    op.drop_constraint("resources_branch_id_fkey", "resources", type_="foreignkey")
    op.create_foreign_key("fk_resources_tenant_branch", "resources", "branches",
        ["tenant_id", "branch_id"], ["tenant_id", "id"], ondelete="CASCADE")

    for column, target in (("branch_id", "branches"), ("customer_id", "customers"),
                           ("service_id", "services"), ("staff_id", "staff"),
                           ("resource_id", "resources")):
        op.drop_constraint(f"appointments_{column}_fkey", "appointments", type_="foreignkey")
        op.create_foreign_key(f"fk_appointment_tenant_{column.removesuffix('_id')}",
            "appointments", target, ["tenant_id", column], ["tenant_id", "id"])

    op.drop_constraint("audit_logs_actor_user_id_fkey", "audit_logs", type_="foreignkey")
    op.create_foreign_key("fk_audit_tenant_actor", "audit_logs", "users",
        ["tenant_id", "actor_user_id"], ["tenant_id", "id"])

    op.create_index("ix_staff_branch_id", "staff", ["branch_id"])
    op.create_index("ix_resources_branch_id", "resources", ["branch_id"])
    op.create_index("ix_appointments_branch_id", "appointments", ["branch_id"])

    # Restaura y fuerza las políticas existentes de R4.0, sin el bypass auth_lookup.
    for table in BACKFILL_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON users USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")

    op.create_table("refresh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("jti_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"], ondelete="CASCADE"))
    op.create_index("ix_refresh_sessions_tenant_id", "refresh_sessions", ["tenant_id"])
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_tenant_user", "refresh_sessions", ["tenant_id", "user_id"])

    op.create_table("user_branch_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "branch_id", name="uq_user_branch_access"),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE"))
    op.create_index("ix_user_branch_access_tenant_id", "user_branch_access", ["tenant_id"])

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")

    # auth_identities solo expone el índice mínimo de login; no permite modificarlo
    # ni borrarlo directamente desde el runtime.
    op.execute("REVOKE UPDATE, DELETE ON auth_identities FROM agendavoice_app")
    op.execute("GRANT SELECT, INSERT ON auth_identities TO agendavoice_app")


def downgrade():
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")

    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    op.drop_index("ix_auth_identities_tenant_id", table_name="auth_identities")
    op.drop_table("auth_identities")

    op.drop_index("ix_appointments_branch_id", table_name="appointments")
    op.drop_index("ix_resources_branch_id", table_name="resources")
    op.drop_index("ix_staff_branch_id", table_name="staff")
    op.drop_constraint("fk_audit_tenant_actor", "audit_logs", type_="foreignkey")
    op.create_foreign_key("audit_logs_actor_user_id_fkey", "audit_logs", "users", ["actor_user_id"], ["id"])
    for column, target in (("branch_id", "branches"), ("customer_id", "customers"),
                           ("service_id", "services"), ("staff_id", "staff"),
                           ("resource_id", "resources")):
        op.drop_constraint(f"fk_appointment_tenant_{column.removesuffix('_id')}", "appointments", type_="foreignkey")
        op.create_foreign_key(f"appointments_{column}_fkey", "appointments", target, [column], ["id"])
    op.drop_constraint("fk_staff_tenant_branch", "staff", type_="foreignkey")
    op.create_foreign_key("staff_branch_id_fkey", "staff", "branches", ["branch_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("fk_resources_tenant_branch", "resources", type_="foreignkey")
    op.create_foreign_key("resources_branch_id_fkey", "resources", "branches", ["branch_id"], ["id"], ondelete="CASCADE")

    for name, table in (("uq_resources_tenant_id", "resources"), ("uq_staff_tenant_id", "staff"),
                        ("uq_services_tenant_id", "services"), ("uq_customers_tenant_id", "customers"),
                        ("uq_branches_tenant_id", "branches"), ("uq_users_tenant_id", "users")):
        op.drop_constraint(name, table, type_="unique")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    # Compatibilidad con el login histórico R4.0 al volver atrás.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.execute("CREATE POLICY tenant_isolation ON users USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer OR current_setting('app.auth_lookup', true) = 'on') WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")
