from sqlalchemy import text
from sqlalchemy.orm import Session


def set_tenant_context(db: Session, tenant_id: int) -> None:
    """Bind the authenticated tenant_id to the current session and active SQL transaction."""
    if tenant_id <= 0:
        raise ValueError("tenant_id must be positive")
    db.info["tenant_id"] = tenant_id
    db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
               {"tenant_id": str(tenant_id)})
