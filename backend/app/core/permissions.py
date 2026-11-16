from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import current_user
from app.modules.identity.models import UserBranchAccess


def allow_roles(*roles: str):
    def dependency(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return user
    return dependency


def accessible_branch_ids(db: Session, user) -> list[int] | None:
    """None significa acceso a todas las sucursales del tenant."""
    if user.role in {"SUPER_ADMIN", "TENANT_ADMIN"}:
        return None
    return [row.branch_id for row in db.query(UserBranchAccess.branch_id)
            .filter(UserBranchAccess.tenant_id == user.tenant_id,
                    UserBranchAccess.user_id == user.id).all()]


def assert_branch_access(db: Session, user, branch_id: int) -> None:
    allowed = accessible_branch_ids(db, user)
    if allowed is not None and branch_id not in allowed:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
