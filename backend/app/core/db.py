from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

@event.listens_for(Session, "after_begin")
def _apply_transaction_context(session: Session, transaction, connection) -> None:
    """Re-applies the transaction-local tenant context at the start of EVERY transaction.

    PostgreSQL clears GUCs established with SET LOCAL upon COMMIT/ROLLBACK.
    Storing tenant_id in session.info restores it safely on subsequent transactions
    within the same request without polluting pooled connections.
    """
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None:
        connection.execute(text("SELECT set_config('app.tenant_id', :value, true)"), {"value": str(tenant_id)})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.info.clear()
        db.close()
