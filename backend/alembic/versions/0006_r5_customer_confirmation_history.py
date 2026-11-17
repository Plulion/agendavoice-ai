"""R5.0: customer profiles, consent, professional preferences, history and email confirmation."""
from alembic import op
import sqlalchemy as sa

revision = "0006_r5_customer_history"
down_revision = "0005_r422_customer_home_branch"
branch_labels = None
depends_on = None

def upgrade():
    op.create_unique_constraint("uq_appointments_tenant_id", "appointments", ["tenant_id", "id"])
    op.add_column("customers", sa.Column("first_name", sa.String(100), nullable=True))
    op.add_column("customers", sa.Column("last_name", sa.String(100), nullable=True))
    op.add_column("customers", sa.Column("rut", sa.String(12), nullable=True))
    op.create_index("uq_customer_tenant_rut", "customers", ["tenant_id", "rut"], unique=True, postgresql_where=sa.text("rut IS NOT NULL"))
    op.create_table("customer_consents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("consent_type", sa.String(40), nullable=False), sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(30), nullable=False), sa.Column("source", sa.String(30), nullable=False, server_default="WEB"), sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_customer_consent_customer"))
    op.create_table("customer_staff_preferences",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("branch_id", sa.Integer(), nullable=False), sa.Column("staff_id", sa.Integer(), nullable=False), sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_customer_staff_pref_customer"),
        sa.ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], ondelete="CASCADE", name="fk_customer_staff_pref_staff"),
        sa.ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], name="fk_customer_staff_pref_service"))
    op.create_index("ix_customer_staff_pref_lookup", "customer_staff_preferences", ["tenant_id", "customer_id", "branch_id"])
    op.create_index("uq_customer_staff_pref_primary_scope", "customer_staff_preferences", ["tenant_id", "customer_id", "branch_id", sa.text("COALESCE(service_id, 0)")], unique=True, postgresql_where=sa.text("is_primary"))
    op.create_table("service_history",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False, unique=True), sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False), sa.Column("service_name_snapshot", sa.String(120), nullable=False), sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("staff_name_snapshot", sa.String(120), nullable=True), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"], ondelete="CASCADE", name="fk_service_history_appointment"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_service_history_customer"))
    op.create_index("ix_service_history_customer_date", "service_history", ["tenant_id", "customer_id", "starts_at"])
    op.create_table("waitlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False), sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=True), sa.Column("preferred_from", sa.DateTime(timezone=True), nullable=False), sa.Column("preferred_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("status", sa.String(20), nullable=False, server_default="WAITING"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_waitlist_branch"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_waitlist_customer"),
        sa.ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], name="fk_waitlist_service"),
        sa.ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], name="fk_waitlist_staff"),
        sa.CheckConstraint("preferred_to > preferred_from", name="ck_waitlist_range"), sa.CheckConstraint("status IN ('WAITING','OFFERED','BOOKED','CANCELLED')", name="ck_waitlist_status"))
    op.create_index("ix_waitlist_matching", "waitlist_entries", ["tenant_id", "branch_id", "service_id", "status", "preferred_from", "preferred_to"])
    op.create_table("appointment_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"], ondelete="CASCADE", name="fk_appointment_confirmation_appointment"))
    op.create_table("email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True), sa.Column("recipient", sa.String(255), nullable=False), sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"], ondelete="CASCADE", name="fk_email_outbox_appointment"))
    op.create_index("ix_email_outbox_pending", "email_outbox", ["tenant_id", "status", "created_at"])
    # Apply the same tenant isolation policy used by the existing business tables.
    for table in ("customer_consents", "customer_staff_preferences", "service_history", "appointment_confirmations", "email_outbox", "waitlist_entries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer)")
    op.execute("CREATE POLICY confirmation_token_public_lookup ON appointment_confirmations FOR SELECT USING (token_hash = current_setting('app.confirmation_token_hash', true))")

def downgrade():
    for table in ("email_outbox", "appointment_confirmations", "service_history", "customer_staff_preferences", "customer_consents", "waitlist_entries"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
    op.drop_index("uq_customer_tenant_rut", table_name="customers")
    op.drop_constraint("uq_appointments_tenant_id", "appointments", type_="unique")
    op.drop_column("customers", "rut")
    op.drop_column("customers", "last_name")
    op.drop_column("customers", "first_name")
