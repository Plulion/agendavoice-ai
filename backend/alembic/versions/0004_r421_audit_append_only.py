"""R4.2.1: Enforce append-only audit_logs for the runtime database role.

Revokes UPDATE and DELETE on audit_logs from agendavoice_app so application bugs
or compromised runtime queries cannot alter or erase historical audit records.
"""
from alembic import op

revision = "0004_r421_audit_append_only"
down_revision = "0003_r42_universal_scheduling"
branch_labels = None
depends_on = None


def upgrade():
    # Guard with pg_roles check so migrations succeed even if the runtime role is created later.
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
