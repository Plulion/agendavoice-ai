"""Initial AgendaVoice shared core and salon vertical."""
from alembic import op
import sqlalchemy as sa
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("tenants", sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("name",sa.String(160),nullable=False),sa.Column("slug",sa.String(100),nullable=False,unique=True),
        sa.Column("status",sa.String(20),nullable=False,server_default="ACTIVE"),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_table("users",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("email",sa.String(255),nullable=False,unique=True),
        sa.Column("password_hash",sa.String(255),nullable=False),sa.Column("role",sa.String(30),nullable=False,server_default="TENANT_ADMIN"),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_table("branches",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("address",sa.String(255)),sa.Column("phone",sa.String(40)),
        sa.Column("timezone",sa.String(64),nullable=False,server_default="America/Santiago"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("tenant_id","name",name="uq_branch_tenant_name"))
    op.create_table("customers",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(160),nullable=False),sa.Column("phone",sa.String(40),nullable=False),sa.Column("email",sa.String(255)),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.UniqueConstraint("tenant_id","phone",name="uq_customer_tenant_phone"))
    op.create_table("services",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("description",sa.String(500)),sa.Column("duration_minutes",sa.Integer(),nullable=False),
        sa.Column("buffer_minutes",sa.Integer(),nullable=False,server_default="0"),sa.Column("price",sa.Numeric(12,2),nullable=False),
        sa.Column("currency",sa.String(3),nullable=False,server_default="CLP"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("tenant_id","name",name="uq_service_tenant_name"))
    op.create_table("staff",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("specialties",sa.String(500),nullable=False,server_default=""),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table("resources",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="CASCADE"),nullable=False),
        sa.Column("resource_type",sa.String(40),nullable=False,server_default="CHAIR"),sa.Column("name",sa.String(120),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table("appointments",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id"),nullable=False),
        sa.Column("customer_id",sa.Integer(),sa.ForeignKey("customers.id"),nullable=False),
        sa.Column("service_id",sa.Integer(),sa.ForeignKey("services.id"),nullable=False),
        sa.Column("staff_id",sa.Integer(),sa.ForeignKey("staff.id")),sa.Column("resource_id",sa.Integer(),sa.ForeignKey("resources.id")),
        sa.Column("starts_at",sa.DateTime(timezone=True),nullable=False),sa.Column("ends_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("status",sa.String(20),nullable=False,server_default="CONFIRMED"),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.CheckConstraint("ends_at > starts_at",name="ck_appointment_positive_range"))
    op.create_table("subscriptions",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False,unique=True),
        sa.Column("plan",sa.String(30),nullable=False,server_default="STARTER"),sa.Column("status",sa.String(20),nullable=False,server_default="TRIAL"),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_table("audit_logs",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("tenant_id",sa.Integer(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("actor_user_id",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("action",sa.String(100),nullable=False),
        sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(80)),
        sa.Column("details",sa.JSON(),nullable=False,server_default=sa.text("'{}'")),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    for table in ("users","branches","customers","services","staff","resources","appointments","subscriptions","audit_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        extra = " OR current_setting('app.auth_lookup', true) = 'on'" if table == "users" else ""
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int{extra}) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)")
    for table in ("users","branches","customers","services","staff","resources","appointments","audit_logs"):
        op.create_index(f"ix_{table}_tenant_id",table,["tenant_id"])
    op.create_index("ix_appointments_tenant_start","appointments",["tenant_id","starts_at"])
    op.create_index("ix_appointments_staff_range","appointments",["staff_id","starts_at","ends_at"])

def downgrade():
    for table in ("audit_logs","subscriptions","appointments","resources","staff","services","customers","branches","users","tenants"):
        op.drop_table(table)
