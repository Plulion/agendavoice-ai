from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.core.tenant_context import set_tenant_context
from app.modules.identity.models import User
from app.modules.tenants.models import Tenant

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(value: str) -> str:
    return pwd_context.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(value, hashed)
    except (ValueError, TypeError):
        return False


def _encode_token(payload: dict) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def issue_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return _encode_token({"sub": str(user.id), "tenant_id": user.tenant_id,
        "role": user.role, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access"})


def new_refresh_token(user: User) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    jti = str(uuid4())
    expires = now + timedelta(days=settings.refresh_token_days)
    token = _encode_token({"sub": str(user.id), "tenant_id": user.tenant_id,
        "jti": jti, "iat": now, "exp": expires, "type": "refresh"})
    return token, sha256(jti.encode()).hexdigest(), expires


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh" or not payload.get("jti"):
            raise ValueError("wrong token type")
        return payload
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Refresh token inválido o expirado")


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Autenticación requerida", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id, tenant_id = int(payload["sub"]), int(payload["tenant_id"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Token inválido o expirado")
    set_tenant_context(db, tenant_id)
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id,
                                 User.active.is_(True)).first()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.status == "ACTIVE").first()
    if not user or not tenant:
        raise HTTPException(401, "Usuario no autorizado")
    return user


def require_roles(*roles):
    return __import__("app.core.permissions", fromlist=["allow_roles"]).allow_roles(*roles)
