"""R4.2.2: sucursal de origen de clientes para filtrar por acceso.

Antes, cualquier usuario de la empresa veía todos los clientes. Ahora un cliente es visible
para su sucursal de origen o para las sucursales donde tiene reservas.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_r422_customer_home_branch"
down_revision = "0004_r421_audit_append_only"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("home_branch_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_customer_home_branch", "customers", "branches",
                          ["tenant_id", "home_branch_id"], ["tenant_id", "id"])
    op.create_index("ix_customers_tenant_home_branch", "customers", ["tenant_id", "home_branch_id"])

    # FORCE RLS también afecta al propietario: sin contexto de tenant, el UPDATE no vería filas
    # y la consulta de appointments devolvería vacío. Se desactiva solo en esta transacción DDL.
    op.execute("ALTER TABLE customers DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments DISABLE ROW LEVEL SECURITY")
    # Relleno inicial: la sucursal de la primera reserva del cliente.
    op.execute("""
        UPDATE customers AS c
        SET home_branch_id = first_visit.branch_id
        FROM (
            SELECT DISTINCT ON (tenant_id, customer_id) tenant_id, customer_id, branch_id
            FROM appointments
            ORDER BY tenant_id, customer_id, starts_at
        ) AS first_visit
        WHERE c.tenant_id = first_visit.tenant_id
          AND c.id = first_visit.customer_id
          AND c.home_branch_id IS NULL
    """)
    op.execute("ALTER TABLE customers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE customers FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments FORCE ROW LEVEL SECURITY")


def downgrade():
    op.drop_index("ix_customers_tenant_home_branch", table_name="customers")
    op.drop_constraint("fk_customer_home_branch", "customers", type_="foreignkey")
    op.drop_column("customers", "home_branch_id")
