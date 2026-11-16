"""R4.2.1: auditoría de solo inserción para el rol de runtime.

Antes, los privilegios por defecto de infra/postgres/init.sql daban UPDATE y DELETE
sobre todas las tablas al rol agendavoice_app, incluida audit_logs. Un fallo de
aplicación o una inyección SQL podía borrar el rastro de auditoría.
"""
from alembic import op

revision = "0004_r421_audit_append_only"
down_revision = "0003_r42_universal_scheduling"
branch_labels = None
depends_on = None


def upgrade():
    # DO $$ evita fallar en entornos de prueba donde el rol de runtime aún no existe.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agendavoice_app') THEN
                REVOKE UPDATE, DELETE ON audit_logs FROM agendavoice_app;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agendavoice_app') THEN
                GRANT UPDATE, DELETE ON audit_logs TO agendavoice_app;
            END IF;
        END $$;
    """)
