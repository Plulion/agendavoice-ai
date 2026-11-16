from pathlib import Path

def test_migration_enables_and_forces_rls_for_tenant_tables():
    migration = Path("alembic/versions/0001_initial.py").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "app.tenant_id" in migration
