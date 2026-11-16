from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

@event.listens_for(Session, "after_begin")
def _apply_transaction_context(session: Session, transaction, connection) -> None:
    """Reaplica el contexto local en CADA transacción de la sesión.

    PostgreSQL elimina los GUC establecidos con SET LOCAL al hacer COMMIT/ROLLBACK.
    Guardar el tenant en session.info permite restaurarlo de forma segura al iniciar
    la siguiente transacción, sin contaminar conexiones reutilizadas del pool.
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
