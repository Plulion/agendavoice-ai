from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import logging
from uuid import uuid4
import secrets
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, select, false
from sqlalchemy.exc import IntegrityError
from redis import Redis
from slugify import slugify
from app.core.config import settings
from app.core.db import get_db
from app.core.tenant_context import set_tenant_context
from app.core.security import (hash_password, verify_password, issue_access_token,
    new_refresh_token, decode_refresh_token, current_user, require_roles)
from app.core.permissions import accessible_branch_ids, assert_branch_access
from app.core.rate_limiter import FixedWindowLimiter
from app.core.session_rules import is_concurrent_reuse
from app.modules.tenants.models import Tenant
from app.modules.identity.models import User, AuthIdentity, RefreshSession, UserBranchAccess
from app.modules.branches.models import Branch
from app.modules.customers.models import Customer
from app.modules.customers.rut import is_valid_chilean_rut, normalize_rut
from app.modules.customers.relationship_models import CustomerConsent, CustomerStaffPreference, ServiceHistory
from app.modules.notifications.models import AppointmentConfirmation, EmailOutbox
from app.modules.notifications.email import send_email
from app.modules.notifications.formatting import (
    format_appointment_local_time,
    is_valid_confirmation_token_format,
    resolve_confirmation_recipient,
)
from app.modules.catalog.models import Service
from app.modules.scheduling.models import (Staff, Resource, Appointment, BranchHours, BranchBreak, StaffHours, StaffBreak, ResourceHours, ResourceBreak)
from app.modules.scheduling.relationship_models import WaitlistEntry
from app.modules.subscriptions.models import Subscription
from app.modules.audit.models import AuditLog
from app.modules.scheduling.availability import WeeklyWindow, WeeklyBreak, interval_fits_schedule, local_slot_to_utc, iter_local_slots
from app.schemas import (RegisterIn, LoginIn, RefreshIn, TokenOut, UserCreateIn,
    BranchIn, ServiceIn, StaffIn, CustomerIn, AppointmentIn, AppointmentOut,
    ResourceIn, ScheduleConfigIn, AppointmentCancelIn, PhoneResolveIn, OmnichannelTurnIn,
    CustomerProfileUpdateIn, CustomerConsentIn, StaffPreferenceIn, WaitlistIn, LocalChatIn, AppointmentConfirmationIn)
from app.modules.customers.visibility import normalize_phone, sanitize_cross_branch_customer
from app.integrations.gemini.agent import extract_email_from_text, run_branch_conversation_turn
from app.integrations.llm.ollama import OllamaChatProvider

app = FastAPI(title="AgendaVoice AI API", version="5.0.3", description="Universal multi-tenant customer, scheduling and engagement platform")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

logger = logging.getLogger(__name__)

# Fixed-window rate limiter by IP/email on authentication endpoints. Backed by Redis across workers.
_limiter = FixedWindowLimiter(redis_client=Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5))


def issue_token_pair(db: Session, user: User) -> dict:
    refresh_token, jti_hash, expires_at = new_refresh_token(user)
    db.add(RefreshSession(tenant_id=user.tenant_id, user_id=user.id,
                          jti_hash=jti_hash, expires_at=expires_at))
    return {"access_token": issue_access_token(user), "refresh_token": refresh_token,
            "expires_in": settings.access_token_minutes * 60}


def audit(db, user, action, entity_type, entity_id, details=None):
    db.add(AuditLog(tenant_id=user.tenant_id, actor_user_id=user.id, action=action,
        entity_type=entity_type, entity_id=str(entity_id) if entity_id else None, details=details or {}))


def expire_pending_appointments(db, tenant_id: int) -> int:
    """Release appointments whose email confirmation token expired."""
    result = db.execute(text("""
        UPDATE appointments AS a SET status='CANCELLED', cancelled_at=now(),
            cancellation_reason='El plazo para confirmar la cita expiró'
        WHERE a.tenant_id=:tenant_id AND a.status='PENDING'
          AND EXISTS (SELECT 1 FROM appointment_confirmations c
            WHERE c.tenant_id=a.tenant_id AND c.appointment_id=a.id AND c.expires_at < now()
              AND c.confirmed_at IS NULL)
    """), {"tenant_id": tenant_id})
    return result.rowcount or 0


ACTIVE_APPOINTMENT_STATUSES = ("PENDING", "CONFIRMED")


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    if not settings.rate_limit_enabled:
        return
    if not _limiter.hit(key, limit, window_seconds):
        raise HTTPException(429, "Demasiados intentos. Intenta nuevamente más tarde.",
                            headers={"Retry-After": str(window_seconds)})


def _customer_scope(db, user, query):
    """Filter customers by branch scope: tenant admins see all; branch roles see only their branches."""
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        return query
    if not allowed:
        return query.filter(false())
    visited = select(Appointment.customer_id).where(
        Appointment.tenant_id == user.tenant_id, Appointment.branch_id.in_(allowed))
    return query.filter(or_(Customer.home_branch_id.in_(allowed), Customer.id.in_(visited)))


def _customer_visible(db, user, customer) -> bool:
    """Evaluate branch visibility for a single customer record (see modules/customers/visibility.py)."""
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        return True
    if not allowed:
        return False
    if customer.home_branch_id is not None and customer.home_branch_id in allowed:
        return True
    return db.query(Appointment.id).filter(Appointment.tenant_id == user.tenant_id,
        Appointment.customer_id == customer.id, Appointment.branch_id.in_(allowed)).first() is not None


def _resolve_or_create_customer_by_phone(
    db: Session,
    user: User,
    branch_id: int,
    phone: str,
    name: str | None = None,
    email: str | None = None,
) -> tuple[Customer, bool, bool]:
    """Industry-standard Blind Upsert: resolve customer by exact normalized phone within the tenant
    or create a new customer assigned to the current branch as home_branch_id.
    Returns (customer, was_existing_other_branch, created_new_customer).
    """
    assert_branch_access(db, user, branch_id)
    clean_phone = normalize_phone(phone) or phone.strip()
    existing = db.query(Customer).filter(
        Customer.tenant_id == user.tenant_id,
        or_(Customer.phone == clean_phone, Customer.phone == phone.strip()),
    ).first()
    if existing is not None:
        was_other = not _customer_visible(db, user, existing)
        if was_other:
            audit(
                db,
                user,
                "customer.cross_branch_linked",
                "customer",
                existing.id,
                {"branch_id": branch_id},
            )
        return existing, was_other, False

    if not name or len(name.strip()) < 2:
        raise HTTPException(422, "El cliente no está registrado; indique su nombre para crearlo")

    obj = Customer(
        tenant_id=user.tenant_id,
        name=name.strip(),
        phone=clean_phone,
        email=email,
        home_branch_id=branch_id,
    )
    db.add(obj)
    db.flush()
    audit(db, user, "customer.created", "customer", obj.id, {"home_branch_id": branch_id})
    return obj, False, True


def _weekly_windows(rows):
    return [WeeklyWindow(row.weekday, row.opens_at, row.closes_at, row.is_closed) for row in rows]


def _weekly_breaks(rows):
    return [WeeklyBreak(row.weekday, row.starts_at, row.ends_at) for row in rows]


def _branch_schedule(db, tenant_id: int, branch_id: int):
    hours = db.query(BranchHours).filter_by(tenant_id=tenant_id, branch_id=branch_id).all()
    breaks = db.query(BranchBreak).filter_by(tenant_id=tenant_id, branch_id=branch_id).all()
    return _weekly_windows(hours), _weekly_breaks(breaks), bool(hours)


def _staff_schedule(db, tenant_id: int, branch_id: int, staff_id: int, branch_hours, branch_breaks):
    hours_rows = db.query(StaffHours).filter_by(tenant_id=tenant_id, branch_id=branch_id, staff_id=staff_id).all()
    breaks_rows = db.query(StaffBreak).filter_by(tenant_id=tenant_id, branch_id=branch_id, staff_id=staff_id).all()
    if not hours_rows:
        return branch_hours, branch_breaks, True
    return _weekly_windows(hours_rows), _weekly_breaks(breaks_rows), True


def _resource_schedule(db, tenant_id: int, branch_id: int, resource_id: int, branch_hours, branch_breaks):
    hours_rows = db.query(ResourceHours).filter_by(tenant_id=tenant_id, branch_id=branch_id, resource_id=resource_id).all()
    breaks_rows = db.query(ResourceBreak).filter_by(tenant_id=tenant_id, branch_id=branch_id, resource_id=resource_id).all()
    if not hours_rows:
        return branch_hours, branch_breaks, True
    return _weekly_windows(hours_rows), _weekly_breaks(breaks_rows), True


def _schedule_payload(db, hours_model, breaks_model, filters):
    hours = db.query(hours_model).filter_by(**filters).order_by(hours_model.weekday).all()
    breaks = db.query(breaks_model).filter_by(**filters).order_by(breaks_model.weekday, breaks_model.starts_at).all()
    return {
        "hours": [{"weekday": row.weekday, "is_closed": row.is_closed,
                   "opens_at": row.opens_at.isoformat() if row.opens_at else None,
                   "closes_at": row.closes_at.isoformat() if row.closes_at else None} for row in hours],
        "breaks": [{"weekday": row.weekday, "starts_at": row.starts_at.isoformat(),
                    "ends_at": row.ends_at.isoformat()} for row in breaks],
    }


def _replace_schedule(db, user, branch_id, config, hours_model, breaks_model, entity_name=None, entity_id=None):
    filters = {"tenant_id": user.tenant_id, "branch_id": branch_id}
    if entity_name:
        filters[entity_name] = entity_id
    db.query(breaks_model).filter_by(**filters).delete(synchronize_session=False)
    db.query(hours_model).filter_by(**filters).delete(synchronize_session=False)
    for item in config.hours:
        values = item.model_dump()
        db.add(hours_model(**filters, **values))
    for item in config.breaks:
        values = item.model_dump()
        db.add(breaks_model(**filters, **values))


def _check_interval_against_schedules(db, tenant_id, branch, starts, ends, staff_id=None, resource_id=None):
    branch_hours, branch_breaks, configured = _branch_schedule(db, tenant_id, branch.id)
    try:
        branch_fits = configured and interval_fits_schedule(starts, ends, branch.timezone, branch_hours, branch_breaks)
    except ValueError:
        return False, "La sucursal tiene una zona horaria inválida; corrígela antes de reservar"
    if not branch_fits:
        return False, "La reserva está fuera del horario de la sucursal o dentro de una pausa"
    if staff_id is not None:
        staff_hours, staff_breaks, staff_configured = _staff_schedule(
            db, tenant_id, branch.id, staff_id, branch_hours, branch_breaks)
        if not staff_configured or not interval_fits_schedule(starts, ends, branch.timezone, staff_hours, staff_breaks):
            return False, "El profesional no está disponible en ese horario"
    if resource_id is not None:
        resource_hours, resource_breaks, resource_configured = _resource_schedule(
            db, tenant_id, branch.id, resource_id, branch_hours, branch_breaks)
        if not resource_configured or not interval_fits_schedule(starts, ends, branch.timezone, resource_hours, resource_breaks):
            return False, "El recurso no está disponible en ese horario"
    return True, None


@app.get("/health")
def health(db: Session = Depends(get_db)):
    result = {"status": "ok", "database": "ok", "redis": "unknown"}
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        result.update(status="degraded", database="error")
    try:
        Redis.from_url(settings.redis_url, socket_connect_timeout=1).ping()
        result["redis"] = "ok"
    except Exception:
        result["redis"] = "error"
    return result


@app.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(f"register-ip:{client_ip(request)}", 5, 3600)
    email = str(data.email).lower()
    slug_base = slugify(data.company_name)[:70] or "empresa"
    slug = f"{slug_base}-{uuid4().hex[:8]}"
    if db.query(AuthIdentity).filter(AuthIdentity.email == email).first():
        raise HTTPException(409, "El correo ya está registrado")
    try:
        # Reserve sequence ID first so app.tenant_id GUC can be set before inserting into RLS-protected tenants.
        tenant_id = db.execute(text("SELECT nextval(pg_get_serial_sequence('tenants', 'id'))")).scalar_one()
        set_tenant_context(db, tenant_id)
        tenant = Tenant(id=tenant_id, name=data.company_name.strip(), slug=slug)
        db.add(tenant)
        db.flush()
        user = User(tenant_id=tenant.id, name=data.admin_name.strip(), email=email,
                    password_hash=hash_password(data.password), role="TENANT_ADMIN")
        db.add(user)
        db.flush()
        db.add(AuthIdentity(email=email, user_id=user.id, tenant_id=tenant.id))
        db.add(Subscription(tenant_id=tenant.id, plan="STARTER", status="TRIAL"))
        audit(db, user, "tenant.registered", "tenant", tenant.id)
        tokens = issue_token_pair(db, user)
        db.commit()
        return tokens
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No fue posible registrar la empresa con esos datos")


@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = str(data.email).lower()
    enforce_rate_limit(f"login-ip:{client_ip(request)}", 20, 60)
    enforce_rate_limit(f"login-email:{email}", 10, 900)
    # This lookup table stores only email/user_id/tenant_id. Password hash and
    # user profile are queried only after activating the tenant RLS context.
    identity = db.query(AuthIdentity).filter(AuthIdentity.email == email).first()
    if not identity:
        raise HTTPException(401, "Credenciales incorrectas")
    set_tenant_context(db, identity.tenant_id)
    user = db.query(User).filter(User.id == identity.user_id,
        User.tenant_id == identity.tenant_id, User.active.is_(True)).first()
    tenant = db.query(Tenant).filter(Tenant.id == identity.tenant_id, Tenant.status == "ACTIVE").first()
    if not user or not tenant or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Credenciales incorrectas")
    tokens = issue_token_pair(db, user)
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return tokens


@app.post("/auth/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(f"refresh-ip:{client_ip(request)}", 30, 60)
    try:
        payload = decode_refresh_token(data.refresh_token)
        user_id, tenant_id = int(payload["sub"]), int(payload["tenant_id"])
        jti_hash = sha256(payload["jti"].encode()).hexdigest()
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, "Refresh token inválido o expirado")
    set_tenant_context(db, tenant_id)
    session = db.query(RefreshSession).filter(RefreshSession.jti_hash == jti_hash,
        RefreshSession.user_id == user_id, RefreshSession.tenant_id == tenant_id).with_for_update().first()
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id,
                                 User.active.is_(True)).first()
    now = datetime.now(timezone.utc)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.status == "ACTIVE").first()
    if session is not None and session.revoked_at is not None and user is not None:
        if is_concurrent_reuse(session.revoked_at, now):
            # Concurrent refresh within grace window (another tab): reject without revoking active sessions.
            raise HTTPException(401, "Sesión de renovación revocada o expirada")
        # Reuse outside grace window: assume token theft and revoke all active sessions for the user.
        db.query(RefreshSession).filter(RefreshSession.tenant_id == tenant_id,
            RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None)).update(
            {"revoked_at": now}, synchronize_session=False)
        audit(db, user, "auth.refresh_reuse_detected", "user", user.id)
        db.commit()
        raise HTTPException(401, "Sesión de renovación revocada o expirada")
    if not session or session.expires_at <= now or not user or not tenant:
        raise HTTPException(401, "Sesión de renovación revocada o expirada")
    session.revoked_at = now
    tokens = issue_token_pair(db, user)
    audit(db, user, "auth.refresh", "user", user.id)
    db.commit()
    return tokens


@app.post("/auth/logout", status_code=204)
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_refresh_token(data.refresh_token)
    try:
        tenant_id, user_id = int(payload["tenant_id"]), int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, "Refresh token inválido o expirado")
    set_tenant_context(db, tenant_id)
    jti_hash = sha256(payload["jti"].encode()).hexdigest()
    session = db.query(RefreshSession).filter(RefreshSession.jti_hash == jti_hash,
        RefreshSession.user_id == user_id).with_for_update().first()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return None


@app.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    branch_ids = accessible_branch_ids(db, user)
    return {"user_id": user.id, "name": user.name, "email": user.email, "role": user.role,
            "tenant_id": user.tenant_id, "company": tenant.name if tenant else None,
            "branch_ids": branch_ids}


@app.post("/users", status_code=201)
def create_user(data: UserCreateIn, user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")),
                db: Session = Depends(get_db)):
    email = str(data.email).lower()
    if db.query(AuthIdentity).filter(AuthIdentity.email == email).first():
        raise HTTPException(409, "El correo ya está registrado")
    branch_ids = sorted(set(data.branch_ids))
    branches = db.query(Branch).filter(Branch.tenant_id == user.tenant_id,
                                      Branch.id.in_(branch_ids), Branch.active.is_(True)).all()
    if len(branches) != len(branch_ids):
        raise HTTPException(422, "Una o más sucursales no pertenecen a la empresa")
    new_user = User(tenant_id=user.tenant_id, name=data.name.strip(), email=email,
                    password_hash=hash_password(data.password), role=data.role)
    try:
        db.add(new_user)
        db.flush()
        db.add(AuthIdentity(email=email, user_id=new_user.id, tenant_id=user.tenant_id))
        for branch_id in branch_ids:
            db.add(UserBranchAccess(tenant_id=user.tenant_id, user_id=new_user.id, branch_id=branch_id))
        audit(db, user, "user.created", "user", new_user.id, {"role": data.role, "branch_ids": branch_ids})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No fue posible crear el usuario")
    return {"id": new_user.id, "name": new_user.name, "email": new_user.email,
            "role": new_user.role, "branch_ids": branch_ids}


@app.get("/users")
def list_users(user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")),
               db: Session = Depends(get_db)):
    users = db.query(User).filter(User.tenant_id == user.tenant_id).order_by(User.id).all()
    result = []
    for item in users:
        branches = db.query(UserBranchAccess.branch_id).filter(
            UserBranchAccess.tenant_id == user.tenant_id,
            UserBranchAccess.user_id == item.id).all()
        result.append({"id": item.id, "name": item.name, "email": item.email,
            "role": item.role, "active": item.active,
            "branch_ids": [row.branch_id for row in branches]})
    return result


@app.get("/branches")
def list_branches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Branch).filter(Branch.tenant_id == user.tenant_id)
    allowed = accessible_branch_ids(db, user)
    if allowed is not None:
        q = q.filter(Branch.id.in_(allowed))
    return q.order_by(Branch.id).all()


@app.post("/branches", status_code=201)
def create_branch(data: BranchIn, user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")),
                  db: Session = Depends(get_db)):
    obj = Branch(tenant_id=user.tenant_id, **data.model_dump())
    db.add(obj)
    try:
        db.flush()
        audit(db, user, "branch.created", "branch", obj.id)
        db.commit()
        db.refresh(obj)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sucursal con ese nombre")
    return obj


@app.get("/services")
def list_services(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.tenant_id == user.tenant_id,
        Service.active.is_(True)).order_by(Service.name).all()


@app.post("/services", status_code=201)
def create_service(data: ServiceIn, user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")),
                   db: Session = Depends(get_db)):
    obj = Service(tenant_id=user.tenant_id, **data.model_dump())
    db.add(obj)
    try:
        db.flush()
        audit(db, user, "service.created", "service", obj.id)
        db.commit()
        db.refresh(obj)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un servicio con ese nombre")
    return obj


@app.post("/staff", status_code=201)
def create_staff(data: StaffIn, user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER")),
                 db: Session = Depends(get_db)):
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter(Branch.id == data.branch_id,
        Branch.tenant_id == user.tenant_id, Branch.active.is_(True)).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    obj = Staff(tenant_id=user.tenant_id, **data.model_dump())
    db.add(obj)
    db.flush()
    audit(db, user, "staff.created", "staff", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/staff")
def list_staff(branch_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Staff).filter(Staff.tenant_id == user.tenant_id, Staff.active.is_(True))
    allowed = accessible_branch_ids(db, user)
    if branch_id is not None:
        assert_branch_access(db, user, branch_id)
        q = q.filter(Staff.branch_id == branch_id)
    elif allowed is not None:
        q = q.filter(Staff.branch_id.in_(allowed))
    return q.order_by(Staff.name).all()


@app.post("/resources", status_code=201)
def create_resource(data: ResourceIn, user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER")), db: Session = Depends(get_db)):
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter_by(id=data.branch_id, tenant_id=user.tenant_id, active=True).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    obj = Resource(tenant_id=user.tenant_id, **data.model_dump())
    db.add(obj)
    db.flush()
    audit(db, user, "resource.created", "resource", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/resources")
def list_resources(branch_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Resource).filter(Resource.tenant_id == user.tenant_id, Resource.active.is_(True))
    allowed = accessible_branch_ids(db, user)
    if branch_id is not None:
        assert_branch_access(db, user, branch_id)
        q = q.filter(Resource.branch_id == branch_id)
    elif allowed is not None:
        q = q.filter(Resource.branch_id.in_(allowed))
    return q.order_by(Resource.name).all()


@app.get("/branches/{branch_id}/schedule")
def get_branch_schedule(branch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_branch_access(db, user, branch_id)
    branch = db.query(Branch).filter_by(id=branch_id, tenant_id=user.tenant_id).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    return {"branch_id": branch_id, "timezone": branch.timezone,
            **_schedule_payload(db, BranchHours, BranchBreak, {"tenant_id": user.tenant_id, "branch_id": branch_id})}


@app.put("/branches/{branch_id}/schedule")
def set_branch_schedule(branch_id: int, data: ScheduleConfigIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER")), db: Session = Depends(get_db)):
    assert_branch_access(db, user, branch_id)
    branch = db.query(Branch).filter_by(id=branch_id, tenant_id=user.tenant_id, active=True).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    _replace_schedule(db, user, branch_id, data, BranchHours, BranchBreak)
    audit(db, user, "branch.schedule.updated", "branch", branch_id)
    db.commit()
    return {"branch_id": branch_id, "hours": len(data.hours), "breaks": len(data.breaks), "timezone": branch.timezone}


@app.get("/staff/{staff_id}/schedule")
def get_staff_schedule(staff_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    staff = db.query(Staff).filter_by(id=staff_id, tenant_id=user.tenant_id).first()
    if not staff:
        raise HTTPException(404, "Profesional no encontrado")
    assert_branch_access(db, user, staff.branch_id)
    return {"staff_id": staff_id,
            **_schedule_payload(db, StaffHours, StaffBreak, {"tenant_id": user.tenant_id, "branch_id": staff.branch_id, "staff_id": staff_id})}


@app.put("/staff/{staff_id}/schedule")
def set_staff_schedule(staff_id: int, data: ScheduleConfigIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER")), db: Session = Depends(get_db)):
    staff = db.query(Staff).filter_by(id=staff_id, tenant_id=user.tenant_id, active=True).first()
    if not staff:
        raise HTTPException(404, "Profesional no encontrado")
    assert_branch_access(db, user, staff.branch_id)
    _replace_schedule(db, user, staff.branch_id, data, StaffHours, StaffBreak, "staff_id", staff_id)
    audit(db, user, "staff.schedule.updated", "staff", staff_id)
    db.commit()
    return {"staff_id": staff_id, "hours": len(data.hours), "breaks": len(data.breaks)}


@app.get("/resources/{resource_id}/schedule")
def get_resource_schedule(resource_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    resource = db.query(Resource).filter_by(id=resource_id, tenant_id=user.tenant_id).first()
    if not resource:
        raise HTTPException(404, "Recurso no encontrado")
    assert_branch_access(db, user, resource.branch_id)
    return {"resource_id": resource_id,
            **_schedule_payload(db, ResourceHours, ResourceBreak, {"tenant_id": user.tenant_id, "branch_id": resource.branch_id, "resource_id": resource_id})}


@app.put("/resources/{resource_id}/schedule")
def set_resource_schedule(resource_id: int, data: ScheduleConfigIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER")), db: Session = Depends(get_db)):
    resource = db.query(Resource).filter_by(id=resource_id, tenant_id=user.tenant_id, active=True).first()
    if not resource:
        raise HTTPException(404, "Recurso no encontrado")
    assert_branch_access(db, user, resource.branch_id)
    _replace_schedule(db, user, resource.branch_id, data, ResourceHours, ResourceBreak, "resource_id", resource_id)
    audit(db, user, "resource.schedule.updated", "resource", resource_id)
    db.commit()
    return {"resource_id": resource_id, "hours": len(data.hours), "breaks": len(data.breaks)}


@app.post("/customers", status_code=201)
def create_customer(data: CustomerIn, user: User = Depends(require_roles(
        "TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    payload = data.model_dump()
    requested_branch = payload.pop("branch_id")
    payload["phone"] = normalize_phone(payload["phone"])
    if payload.get("first_name") and payload.get("last_name"):
        payload["name"] = f"{payload['first_name'].strip()} {payload['last_name'].strip()}".strip()
    if payload.get("rut"):
        payload["rut"] = normalize_rut(payload["rut"])
        if not is_valid_chilean_rut(payload["rut"]):
            raise HTTPException(422, "El RUT no es válido")
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        home_branch_id = requested_branch
        if home_branch_id is not None and not db.query(Branch.id).filter(Branch.id == home_branch_id,
                Branch.tenant_id == user.tenant_id, Branch.active.is_(True)).first():
            raise HTTPException(422, "La sucursal indicada no pertenece a la empresa")
    elif requested_branch is None:
        if len(allowed) != 1:
            raise HTTPException(422, "Indique la sucursal del cliente")
        home_branch_id = allowed[0]
    else:
        assert_branch_access(db, user, requested_branch)
        home_branch_id = requested_branch
    obj = Customer(tenant_id=user.tenant_id, home_branch_id=home_branch_id, **payload)
    db.add(obj)
    try:
        db.flush()
        audit(db, user, "customer.created", "customer", obj.id, {"home_branch_id": home_branch_id})
        db.commit()
        db.refresh(obj)
    except IntegrityError:
        db.rollback()
        # Generic 409 message: does not leak customer fields belonging to other branches.
        raise HTTPException(409, "El teléfono o RUT ya está registrado en la empresa; un administrador debe revisarlo")
    return obj


@app.get("/customers")
def list_customers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(Customer).filter(Customer.tenant_id == user.tenant_id)
    return _customer_scope(db, user, query).order_by(Customer.name).limit(500).all()


@app.post("/customers/resolve-phone")
def resolve_customer_by_phone(
    data: PhoneResolveIn,
    request: Request,
    user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Allow a branch to resolve or create a customer by exact phone number without admin intervention
    and without exposing history from other branches (protected against enumeration via rate limiting).
    """
    enforce_rate_limit(f"resolve-phone:{user.tenant_id}:{user.id}:{client_ip(request)}", 15, 60)
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter_by(id=data.branch_id, tenant_id=user.tenant_id, active=True).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    customer, was_other, _ = _resolve_or_create_customer_by_phone(
        db, user, data.branch_id, data.phone, data.name, str(data.email) if data.email else None
    )
    db.commit()
    db.refresh(customer)
    if was_other:
        return sanitize_cross_branch_customer(phone=customer.phone)
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "home_branch_id": customer.home_branch_id,
        "cross_branch_linked": False,
    }


@app.get("/audit-logs")
def list_audit_logs(user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")),
                    limit: int = 100, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 500)
    return db.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id).order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()


def _build_confirmation_email(
    *,
    customer_name: str | None,
    service_name: str,
    staff_name: str,
    starts_utc: datetime,
    branch_timezone: str,
    confirmation_url: str,
    include_customer_name: bool,
) -> tuple[str, str]:
    """Render plain-text and HTML confirmation emails in the branch's local timezone (M3 & A2)."""
    local_when = format_appointment_local_time(starts_utc, branch_timezone)
    greeting_text = f"Hola {customer_name}," if (include_customer_name and customer_name) else "Hola,"
    greeting_html = (
        f"<h2>¡Hola {escape(customer_name)}!</h2>"
        if (include_customer_name and customer_name)
        else "<h2>¡Hola!</h2>"
    )
    body = (
        f"{greeting_text}\n\nHemos recibido tu solicitud de cita.\n"
        f"Servicio: {service_name}\nProfesional: {staff_name}\n"
        f"Fecha y hora: {local_when}\n\n"
        f"Confirma tu cita aquí: {confirmation_url}\n"
        f"El enlace vence en {settings.appointment_confirmation_minutes} minutos.\n"
    )
    html_body = (
        "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#222'>"
        f"{greeting_html}<p>Hemos recibido tu solicitud de cita.</p>"
        f"<p><b>Servicio:</b> {escape(service_name)}<br>"
        f"<b>Profesional:</b> {escape(staff_name)}<br>"
        f"<b>Fecha y hora:</b> {escape(local_when)}</p>"
        f"<p><a href='{escape(confirmation_url, quote=True)}' style='display:inline-block;padding:14px 24px;"
        "background:#14532d;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold'>CONFIRMAR MI CITA</a></p>"
        f"<p>Este enlace vence en {settings.appointment_confirmation_minutes} minutos.</p>"
        "<p>Si no solicitaste esta cita, puedes ignorar este mensaje.</p></body></html>"
    )
    return body, html_body


@app.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(
    data: AppointmentIn,
    request: Request,
    user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(f"appointment-create:{user.tenant_id}:{user.id}:{client_ip(request)}", 30, 3600)
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter(Branch.id == data.branch_id,
        Branch.tenant_id == user.tenant_id, Branch.active.is_(True)).first()
    if not branch:
        raise HTTPException(404, "Sucursal, cliente o servicio no encontrado")
    customer = None
    was_other_branch = False
    created_new_customer = False
    if data.customer_phone:
        # Blind Upsert by exact phone: links an existing customer without exposing other branches'
        # history or allowing confirmation emails to be hijacked to an arbitrary address.
        customer, was_other_branch, created_new_customer = _resolve_or_create_customer_by_phone(
            db, user, branch.id, data.customer_phone, data.customer_name,
            str(data.customer_email) if data.customer_email else None,
        )
    elif data.customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == data.customer_id,
            Customer.tenant_id == user.tenant_id).first()
        if customer is not None and not _customer_visible(db, user, customer):
            customer = None  # return generic 404 so sequential customer IDs from other branches cannot be enumerated
    service = db.query(Service).filter(Service.id == data.service_id,
        Service.tenant_id == user.tenant_id, Service.active.is_(True)).first()
    if not branch or not customer or not service:
        raise HTTPException(404, "Sucursal, cliente o servicio no encontrado")
    if data.staff_id is not None:
        staff = db.query(Staff).filter(Staff.id == data.staff_id, Staff.tenant_id == user.tenant_id,
            Staff.branch_id == branch.id, Staff.active.is_(True)).first()
        if not staff:
            raise HTTPException(404, "Profesional no disponible en esta sucursal")
    if data.resource_id is not None:
        resource = db.query(Resource).filter(Resource.id == data.resource_id,
            Resource.tenant_id == user.tenant_id, Resource.branch_id == branch.id,
            Resource.active.is_(True)).first()
        if not resource:
            raise HTTPException(404, "Recurso no disponible en esta sucursal")
    starts = data.starts_at.astimezone(timezone.utc)
    ends = starts + timedelta(minutes=service.duration_minutes + service.buffer_minutes)
    if starts <= datetime.now(timezone.utc):
        raise HTTPException(422, "La reserva debe comenzar en el futuro")
    fits, reason = _check_interval_against_schedules(db, user.tenant_id, branch, starts, ends,
        data.staff_id, data.resource_id)
    if not fits:
        raise HTTPException(409, reason)

    # A2 fix: for existing customers, always send strictly to the stored email address
    # rather than any caller-supplied email.
    recipient = resolve_confirmation_recipient(
        created_new_customer=created_new_customer,
        stored_email=customer.email,
        requested_email=str(data.customer_email) if data.customer_email else None,
    )
    if not recipient:
        if created_new_customer:
            raise HTTPException(422, "Se requiere un correo electrónico para enviar el enlace de confirmación")
        raise HTTPException(
            422,
            "El cliente existente no tiene un correo electrónico registrado para confirmación; "
            "un administrador debe actualizar su perfil.",
        )
    # A4 fix: cap confirmation emails sent to any single recipient address per hour.
    enforce_rate_limit(f"appointment-email:{user.tenant_id}:{recipient.lower()}", 5, 3600)

    expire_pending_appointments(db, user.tenant_id)
    # Ordered transaction advisory locks serialize API requests;
    # PostgreSQL EXCLUDE USING gist constraints provide the physical cross-process guarantee.
    lock_keys = []
    if data.staff_id is not None:
        lock_keys.append(f"tenant:{user.tenant_id}:branch:{branch.id}:staff:{data.staff_id}")
    if data.resource_id is not None:
        lock_keys.append(f"tenant:{user.tenant_id}:branch:{branch.id}:resource:{data.resource_id}")
    for lock_key in sorted(lock_keys):
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": lock_key})
    overlap_filters = []
    if data.staff_id is not None:
        overlap_filters.append(Appointment.staff_id == data.staff_id)
    if data.resource_id is not None:
        overlap_filters.append(Appointment.resource_id == data.resource_id)
    overlaps = db.query(Appointment).filter(Appointment.tenant_id == user.tenant_id,
        Appointment.branch_id == branch.id, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.starts_at < ends, Appointment.ends_at > starts, or_(*overlap_filters)).first()
    if overlaps:
        raise HTTPException(409, "El profesional o recurso ya tiene una reserva en ese horario")
    appointment_values = data.model_dump(exclude={"customer_phone", "customer_name", "customer_email"})
    appointment_values["customer_id"] = customer.id
    appointment_values["starts_at"] = starts
    obj = Appointment(tenant_id=user.tenant_id, **appointment_values,
        ends_at=ends, status="PENDING")
    db.add(obj)
    try:
        db.flush()
        raw_token = secrets.token_urlsafe(32)
        confirmation = AppointmentConfirmation(tenant_id=user.tenant_id, appointment_id=obj.id,
            token_hash=sha256(raw_token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.appointment_confirmation_minutes))
        confirmation_url = f"{settings.public_api_url.rstrip('/')}/public/appointments/confirm?token={raw_token}"
        staff_name = db.query(Staff.name).filter(Staff.id == data.staff_id, Staff.tenant_id == user.tenant_id).scalar() if data.staff_id else "Profesional por asignar"
        body, html_body = _build_confirmation_email(
            customer_name=customer.name,
            service_name=service.name,
            staff_name=staff_name or "Profesional",
            starts_utc=starts,
            branch_timezone=branch.timezone,
            confirmation_url=confirmation_url,
            include_customer_name=not was_other_branch,
        )
        outbox = EmailOutbox(tenant_id=user.tenant_id, appointment_id=obj.id, recipient=recipient,
            subject="Confirma tu cita - AgendaVoice AI",
            body_text="Plantilla de confirmación. El enlace de un solo uso no se conserva en la bandeja de salida.", status="PENDING")
        db.add(confirmation); db.add(outbox)
        audit(db, user, "appointment.created_pending_confirmation", "appointment", obj.id,
              {"starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "cross_branch": was_other_branch})
        db.commit()
        db.refresh(obj); db.refresh(outbox)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El profesional o recurso acaba de ser reservado por otra solicitud")
    # Deliver immediately to local Mailpit or configured SMTP. Failed deliveries remain in outbox.
    try:
        send_email(outbox.recipient, outbox.subject, body, html_body)
        outbox.status = "SENT"; outbox.sent_at = datetime.now(timezone.utc); outbox.attempts += 1
    except Exception as exc:
        outbox.status = "FAILED"; outbox.attempts += 1; outbox.last_error = str(exc)[:500]
    db.commit()
    return obj


@app.post("/appointments/{appointment_id}/resend-confirmation")
def resend_appointment_confirmation(
    appointment_id: int,
    request: Request,
    user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """M4 fix: rotate the confirmation token and resend confirmation email for a PENDING appointment."""
    enforce_rate_limit(f"appointment-resend:{user.tenant_id}:{user.id}:{client_ip(request)}", 15, 3600)
    appointment = db.query(Appointment).filter_by(id=appointment_id, tenant_id=user.tenant_id).with_for_update().first()
    if not appointment:
        raise HTTPException(404, "Reserva no encontrada")
    assert_branch_access(db, user, appointment.branch_id)
    if appointment.status != "PENDING":
        raise HTTPException(409, "Solo se puede reenviar confirmación para reservas pendientes")
    customer = db.query(Customer).filter_by(id=appointment.customer_id, tenant_id=user.tenant_id).first()
    branch = db.query(Branch).filter_by(id=appointment.branch_id, tenant_id=user.tenant_id).first()
    service = db.query(Service).filter_by(id=appointment.service_id, tenant_id=user.tenant_id).first()
    if not customer or not customer.email or not branch or not service:
        raise HTTPException(422, "No es posible reenviar la confirmación para esta reserva")
    enforce_rate_limit(f"appointment-email:{user.tenant_id}:{customer.email.lower()}", 5, 3600)

    now = datetime.now(timezone.utc)
    # Expire previous unconfirmed tokens for this appointment
    db.query(AppointmentConfirmation).filter(
        AppointmentConfirmation.tenant_id == user.tenant_id,
        AppointmentConfirmation.appointment_id == appointment.id,
        AppointmentConfirmation.confirmed_at.is_(None),
        AppointmentConfirmation.expires_at > now,
    ).update({"expires_at": now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    confirmation = AppointmentConfirmation(
        tenant_id=user.tenant_id,
        appointment_id=appointment.id,
        token_hash=sha256(raw_token.encode()).hexdigest(),
        expires_at=now + timedelta(minutes=settings.appointment_confirmation_minutes),
    )
    confirmation_url = f"{settings.public_api_url.rstrip('/')}/public/appointments/confirm?token={raw_token}"
    staff_name = (
        db.query(Staff.name).filter(Staff.id == appointment.staff_id, Staff.tenant_id == user.tenant_id).scalar()
        if appointment.staff_id else "Profesional por asignar"
    )
    body, html_body = _build_confirmation_email(
        customer_name=customer.name,
        service_name=service.name,
        staff_name=staff_name or "Profesional",
        starts_utc=appointment.starts_at,
        branch_timezone=branch.timezone,
        confirmation_url=confirmation_url,
        include_customer_name=_customer_visible(db, user, customer),
    )
    outbox = EmailOutbox(
        tenant_id=user.tenant_id,
        appointment_id=appointment.id,
        recipient=customer.email,
        subject="Confirma tu cita - AgendaVoice AI",
        body_text="Reenvío de confirmación. El enlace de un solo uso no se conserva en la bandeja de salida.",
        status="PENDING",
    )
    db.add(confirmation)
    db.add(outbox)
    audit(db, user, "appointment.confirmation_resent", "appointment", appointment.id)
    db.commit()
    db.refresh(outbox)
    try:
        send_email(outbox.recipient, outbox.subject, body, html_body)
        outbox.status = "SENT"; outbox.sent_at = datetime.now(timezone.utc); outbox.attempts += 1
    except Exception as exc:
        outbox.status = "FAILED"; outbox.attempts += 1; outbox.last_error = str(exc)[:500]
    db.commit()
    return {"appointment_id": appointment.id, "outbox_id": outbox.id, "delivery_status": outbox.status}

@app.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(from_at: datetime | None = None, to_at: datetime | None = None,
                      branch_id: int | None = None, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    q = db.query(Appointment).filter(Appointment.tenant_id == user.tenant_id)
    allowed = accessible_branch_ids(db, user)
    if branch_id is not None:
        assert_branch_access(db, user, branch_id)
        q = q.filter(Appointment.branch_id == branch_id)
    elif allowed is not None:
        q = q.filter(Appointment.branch_id.in_(allowed))
    if from_at:
        if from_at.tzinfo is None or from_at.utcoffset() is None:
            raise HTTPException(422, "from_at debe incluir zona horaria")
        q = q.filter(Appointment.ends_at > from_at.astimezone(timezone.utc))
    if to_at:
        if to_at.tzinfo is None or to_at.utcoffset() is None:
            raise HTTPException(422, "to_at debe incluir zona horaria")
        q = q.filter(Appointment.starts_at < to_at.astimezone(timezone.utc))
    if from_at and to_at and to_at <= from_at:
        raise HTTPException(422, "to_at debe ser posterior a from_at")
    return q.order_by(Appointment.starts_at).limit(1000).all()


@app.get("/availability")
def get_availability(day: date, branch_id: int, service_id: int, staff_id: int | None = None,
        resource_id: int | None = None, slot_minutes: int = 15,
        user: User = Depends(current_user), db: Session = Depends(get_db)):
    if staff_id is None and resource_id is None:
        raise HTTPException(422, "Debe indicar staff_id o resource_id")
    if slot_minutes < 5 or slot_minutes > 60:
        raise HTTPException(422, "slot_minutes debe estar entre 5 y 60")
    assert_branch_access(db, user, branch_id)
    branch = db.query(Branch).filter_by(id=branch_id, tenant_id=user.tenant_id, active=True).first()
    service = db.query(Service).filter_by(id=service_id, tenant_id=user.tenant_id, active=True).first()
    if not branch or not service:
        raise HTTPException(404, "Sucursal o servicio no encontrado")
    if staff_id is not None and not db.query(Staff).filter_by(id=staff_id, tenant_id=user.tenant_id, branch_id=branch_id, active=True).first():
        raise HTTPException(404, "Profesional no disponible")
    if resource_id is not None and not db.query(Resource).filter_by(id=resource_id, tenant_id=user.tenant_id, branch_id=branch_id, active=True).first():
        raise HTTPException(404, "Recurso no disponible")
    branch_hours, branch_breaks, configured = _branch_schedule(db, user.tenant_id, branch_id)
    expired_count = expire_pending_appointments(db, user.tenant_id)
    if expired_count:
        db.commit()  # persist released slots before returning availability
    if not configured:
        return {"day": day.isoformat(), "timezone": branch.timezone, "slots": [], "reason": "Horario de sucursal no configurado"}
    day_hours = next((h for h in branch_hours if h.weekday == day.weekday()), None)
    if not day_hours or day_hours.is_closed:
        return {"day": day.isoformat(), "timezone": branch.timezone, "slots": []}
    total_minutes = service.duration_minutes + service.buffer_minutes
    staff_hours = staff_breaks = None
    resource_hours = resource_breaks = None
    if staff_id is not None:
        staff_hours, staff_breaks, _ = _staff_schedule(db, user.tenant_id, branch_id, staff_id, branch_hours, branch_breaks)
    if resource_id is not None:
        resource_hours, resource_breaks, _ = _resource_schedule(db, user.tenant_id, branch_id, resource_id, branch_hours, branch_breaks)
    try:
        zone = ZoneInfo(branch.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(409, "La sucursal tiene una zona horaria inválida; corrígela antes de consultar disponibilidad")
    # Wide UTC query window: local midnight may not exist during DST transitions.
    # Exact interval overlap is validated per slot afterwards.
    day_start_utc = datetime.combine(day - timedelta(days=1), time(0), tzinfo=timezone.utc)
    day_end_utc = datetime.combine(day + timedelta(days=2), time(0), tzinfo=timezone.utc)
    collision_filters = []
    if staff_id is not None:
        collision_filters.append(Appointment.staff_id == staff_id)
    if resource_id is not None:
        collision_filters.append(Appointment.resource_id == resource_id)
    booked = db.query(Appointment).filter(Appointment.tenant_id == user.tenant_id,
        Appointment.branch_id == branch_id, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.starts_at < day_end_utc, Appointment.ends_at > day_start_utc,
        or_(*collision_filters)).all()
    slots = []
    for clock in iter_local_slots(day, day_hours.opens_at, day_hours.closes_at, slot_minutes):
        starts = local_slot_to_utc(day, clock, branch.timezone)
        if starts is None or starts <= datetime.now(timezone.utc):
            continue
        ends = starts + timedelta(minutes=total_minutes)
        if not interval_fits_schedule(starts, ends, branch.timezone, branch_hours, branch_breaks):
            continue
        if staff_id is not None and not interval_fits_schedule(starts, ends, branch.timezone, staff_hours, staff_breaks):
            continue
        if resource_id is not None and not interval_fits_schedule(starts, ends, branch.timezone, resource_hours, resource_breaks):
            continue
        if any(item.starts_at < ends and item.ends_at > starts for item in booked):
            continue
        slots.append({"starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
                      "local_starts_at": starts.astimezone(zone).isoformat()})
    return {"day": day.isoformat(), "timezone": branch.timezone, "duration_minutes": total_minutes, "slots": slots}


@app.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(appointment_id: int, data: AppointmentCancelIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
        db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter_by(id=appointment_id, tenant_id=user.tenant_id).with_for_update().first()
    if not appointment:
        raise HTTPException(404, "Reserva no encontrada")
    assert_branch_access(db, user, appointment.branch_id)
    if appointment.status == "CANCELLED":
        return appointment
    if appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
        raise HTTPException(409, "Solo se pueden cancelar reservas pendientes o confirmadas")
    appointment.status = "CANCELLED"
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = data.reason
    audit(db, user, "appointment.cancelled", "appointment", appointment.id, {"reason": data.reason})
    db.commit()
    db.refresh(appointment)
    return appointment


@app.post("/channels/omnichannel/turn")
def omnichannel_turn(
    data: OmnichannelTurnIn,
    request: Request,
    user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Execute a conversational AI turn (Gemini Voice or WhatsApp)
    strictly isolated to the specified branch.
    """
    assert_branch_access(db, user, data.branch_id)
    tenant = db.query(Tenant).filter_by(id=user.tenant_id, status="ACTIVE").first()
    branch = db.query(Branch).filter_by(id=data.branch_id, tenant_id=user.tenant_id, active=True).first()
    if not tenant or not branch:
        raise HTTPException(404, "Sucursal no encontrada")

    # N2 fix: extract email from free-text follow-up turns if not passed structurally.
    resolved_email = str(data.customer_email) if data.customer_email else extract_email_from_text(data.message)

    def _slots_fn():
        if not data.service_id or (data.staff_id is None and data.resource_id is None):
            return []
        target_day = (data.starts_at or (datetime.now(timezone.utc) + timedelta(days=1))).date()
        res = get_availability(
            day=target_day,
            branch_id=branch.id,
            service_id=data.service_id,
            staff_id=data.staff_id,
            resource_id=data.resource_id,
            user=user,
            db=db,
        )
        return res.get("slots", [])

    def _book_fn():
        if not data.service_id or not data.starts_at or (data.staff_id is None and data.resource_id is None):
            raise HTTPException(422, "Para agendar se requiere service_id, starts_at y staff_id o resource_id")
        # N4 fix: search both normalized and raw phone formats for compatibility with pre-R5.0.2 records.
        normalized_phone = normalize_phone(data.sender_phone)
        existing_customer = db.query(Customer).filter(
            Customer.tenant_id == user.tenant_id,
            or_(Customer.phone == normalized_phone, Customer.phone == data.sender_phone.strip()),
        ).first()
        if existing_customer is not None:
            if not existing_customer.email:
                return {"status": "ADMIN_EMAIL_REQUIRED"}
            booking_email = None  # Existing customers always receive confirmation at their stored email (A2)
            booking_name = None
        else:
            # N3 fix: avoid creating brand-new customers named generic "Cliente".
            clean_name = (data.sender_name or "").strip()
            if len(clean_name) < 2 or clean_name.lower() == "cliente":
                return {"status": "NAME_REQUIRED"}
            if not resolved_email:
                return {"status": "EMAIL_REQUIRED"}
            booking_email = resolved_email
            booking_name = clean_name
        appt = create_appointment(
            data=AppointmentIn(
                branch_id=branch.id,
                customer_phone=data.sender_phone,
                customer_name=booking_name,
                customer_email=booking_email,
                service_id=data.service_id,
                staff_id=data.staff_id,
                resource_id=data.resource_id,
                starts_at=data.starts_at,
            ),
            request=request,
            user=user,
            db=db,
        )
        return {"id": appt.id, "starts_at": appt.starts_at.isoformat(), "status": appt.status}

    return run_branch_conversation_turn(
        company_name=tenant.name,
        branch_name=branch.name,
        branch_timezone=branch.timezone,
        sender_phone=data.sender_phone,
        sender_name=data.sender_name,
        message=data.message,
        check_availability_fn=_slots_fn,
        book_appointment_fn=_book_fn if (data.service_id and data.starts_at) else None,
    )

@app.post("/ai/local/chat")
def local_ai_chat(data: LocalChatIn, user: User = Depends(current_user)):
    """Local LLM smoke test. The model cannot invoke tools or access tenant data."""
    messages = []
    if data.system_prompt:
        messages.append({"role": "system", "content": data.system_prompt})
    else:
        messages.append({"role": "system", "content": "Eres un asistente de atención de una peluquería. Responde en español, con claridad. No inventes disponibilidad, precios ni datos de clientes."})
    messages.append({"role": "user", "content": data.message})
    try:
        answer = OllamaChatProvider().chat(messages)
    except RuntimeError as exc:
        logger.warning("Local Ollama provider unavailable: %s", exc)
        raise HTTPException(503, "El servicio de IA local no está disponible en este momento")
    return {"provider": "ollama-local", "model": settings.ollama_model, "answer": answer}


@app.post("/waitlist", status_code=201)
def create_waitlist_entry(data: WaitlistIn, user: User = Depends(require_roles(
        "TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    assert_branch_access(db, user, data.branch_id)
    customer = db.query(Customer).filter_by(id=data.customer_id, tenant_id=user.tenant_id).first()
    service = db.query(Service).filter_by(id=data.service_id, tenant_id=user.tenant_id, active=True).first()
    if not customer or not _customer_visible(db, user, customer) or not service:
        raise HTTPException(404, "Cliente o servicio no encontrado")
    if data.staff_id and not db.query(Staff).filter_by(id=data.staff_id, tenant_id=user.tenant_id,
            branch_id=data.branch_id, active=True).first():
        raise HTTPException(404, "Profesional no disponible en la sucursal")
    item = WaitlistEntry(tenant_id=user.tenant_id, **data.model_dump())
    db.add(item); audit(db, user, "waitlist.created", "waitlist", None,
        {"customer_id": data.customer_id, "service_id": data.service_id})
    db.commit(); db.refresh(item)
    return {"id": item.id, "status": item.status, "preferred_from": item.preferred_from,
            "preferred_to": item.preferred_to}


@app.get("/waitlist")
def list_waitlist(branch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_branch_access(db, user, branch_id)
    return db.query(WaitlistEntry).filter_by(tenant_id=user.tenant_id, branch_id=branch_id,
        status="WAITING").order_by(WaitlistEntry.created_at).limit(500).all()


@app.get("/public/appointments/confirm", response_class=HTMLResponse)
def preview_appointment_confirmation(token: str, request: Request, db: Session = Depends(get_db)):
    """Safe landing page: GET never changes appointment state (mail scanners may prefetch links)."""
    enforce_rate_limit(f"appointment-preview:{client_ip(request)}", 30, 300)
    if not is_valid_confirmation_token_format(token):
        raise HTTPException(400, "Enlace de confirmación inválido")
    token_hash = sha256(token.encode()).hexdigest()
    db.execute(text("SELECT set_config('app.confirmation_token_hash', :value, true)"), {"value": token_hash})
    confirmation = db.query(AppointmentConfirmation).filter_by(token_hash=token_hash).first()
    if not confirmation:
        raise HTTPException(404, "Enlace de confirmación inválido o ya no disponible")
    if confirmation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "El enlace de confirmación ha vencido")
    token_json = json.dumps(token)
    return HTMLResponse(
        "<!doctype html><html lang='es'><meta charset='utf-8'><title>Confirmar cita</title>"
        "<main><h1>Confirma tu cita</h1><p>Presiona el botón para confirmar tu reserva.</p>"
        "<button id='confirm'>Confirmar mi cita</button><p id='result' role='status'></p></main>"
        "<script>document.getElementById('confirm').addEventListener('click', async () => {"
        "const b=document.getElementById('confirm'); b.disabled=true;"
        f"const r=await fetch('/public/appointments/confirm',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:{token_json}}})}});"
        "document.getElementById('result').textContent=r.ok?'¡Tu cita está confirmada!':(await r.text());"
        "});</script></html>"
    )


@app.post("/public/appointments/confirm", response_class=HTMLResponse)
def confirm_appointment_by_email(data: AppointmentConfirmationIn, request: Request, db: Session = Depends(get_db)):
    """Explicit confirmation action. GET only renders a landing page."""
    token_hash = sha256(data.token.encode()).hexdigest()
    enforce_rate_limit(f"appointment-confirm:{client_ip(request)}:{token_hash[:16]}", 10, 300)
    db.execute(text("SELECT set_config('app.confirmation_token_hash', :value, true)"), {"value": token_hash})
    confirmation = db.query(AppointmentConfirmation).filter_by(token_hash=token_hash).first()
    if not confirmation:
        raise HTTPException(404, "Enlace de confirmación inválido o ya no disponible")
    set_tenant_context(db, confirmation.tenant_id)
    confirmation = db.query(AppointmentConfirmation).filter_by(id=confirmation.id,
        tenant_id=confirmation.tenant_id).with_for_update().first()
    if not confirmation:
        raise HTTPException(404, "Enlace de confirmación inválido o ya no disponible")
    if confirmation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "El enlace de confirmación ha vencido")
    appointment = db.query(Appointment).filter_by(id=confirmation.appointment_id,
        tenant_id=confirmation.tenant_id).with_for_update().first()
    if not appointment:
        raise HTTPException(404, "Reserva no encontrada")
    if appointment.status == "CONFIRMED":
        return HTMLResponse("<main><h1>Tu cita ya está confirmada</h1></main>")
    if appointment.status != "PENDING":
        raise HTTPException(409, "Esta reserva ya no puede confirmarse")
    appointment.status = "CONFIRMED"
    confirmation.confirmed_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=confirmation.tenant_id, actor_user_id=None,
        action="appointment.confirmed_by_customer", entity_type="appointment",
        entity_id=str(appointment.id), details={"channel": "email"}))
    db.commit()
    return HTMLResponse("<main><h1>¡Tu cita está confirmada!</h1></main>")


@app.put("/customers/{customer_id}/profile")
def update_customer_profile(customer_id: int, data: CustomerProfileUpdateIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN")), db: Session = Depends(get_db)):
    # Customer identity/contact fields are tenant-global; branch operators must not
    # overwrite data shared by every branch.
    customer = db.query(Customer).filter_by(id=customer_id, tenant_id=user.tenant_id).first()
    if not customer:
        raise HTTPException(404, "Cliente no encontrado")
    supplied = data.model_fields_set
    if "first_name" in supplied and data.first_name is not None:
        customer.first_name = data.first_name.strip()
    if "last_name" in supplied and data.last_name is not None:
        customer.last_name = data.last_name.strip()
    if customer.first_name or customer.last_name:
        customer.name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
    if "rut" in supplied:
        rut = normalize_rut(data.rut) if data.rut else None
        if rut and not is_valid_chilean_rut(rut):
            raise HTTPException(422, "El RUT no es válido")
        customer.rut = rut
    if "email" in supplied:
        customer.email = str(data.email) if data.email else None
    audit(db, user, "customer.profile.updated", "customer", customer.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El RUT ya está registrado para otro cliente de esta empresa")
    db.refresh(customer)
    return {"id": customer.id, "name": customer.name, "first_name": customer.first_name,
            "last_name": customer.last_name, "rut": customer.rut, "email": customer.email}


@app.post("/customers/{customer_id}/consents", status_code=201)
def record_customer_consent(customer_id: int, data: CustomerConsentIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter_by(id=customer_id, tenant_id=user.tenant_id).first()
    if not customer or not _customer_visible(db, user, customer):
        raise HTTPException(404, "Cliente no encontrado")
    item = CustomerConsent(tenant_id=user.tenant_id, customer_id=customer_id, **data.model_dump())
    db.add(item); audit(db, user, "customer.consent.recorded", "customer", customer_id,
                       {"consent_type": data.consent_type, "granted": data.granted})
    db.commit(); db.refresh(item)
    return {"id": item.id, "consent_type": item.consent_type, "granted": item.granted,
            "policy_version": item.policy_version, "recorded_at": item.recorded_at}


@app.post("/customers/{customer_id}/staff-preferences", status_code=201)
def add_staff_preference(customer_id: int, data: StaffPreferenceIn,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter_by(id=customer_id, tenant_id=user.tenant_id).first()
    if not customer or not _customer_visible(db, user, customer): raise HTTPException(404, "Cliente no encontrado")
    assert_branch_access(db, user, data.branch_id)
    staff = db.query(Staff).filter_by(id=data.staff_id, tenant_id=user.tenant_id, branch_id=data.branch_id, active=True).first()
    if not staff: raise HTTPException(404, "Profesional no disponible en la sucursal")
    if data.service_id and not db.query(Service).filter_by(id=data.service_id, tenant_id=user.tenant_id, active=True).first():
        raise HTTPException(404, "Servicio no encontrado")
    if data.is_primary:
        q = db.query(CustomerStaffPreference).filter_by(tenant_id=user.tenant_id, customer_id=customer_id,
            branch_id=data.branch_id, service_id=data.service_id)
        for old in q.all(): old.is_primary = False
        db.flush()  # update prior primary before inserting the replacement
    pref = CustomerStaffPreference(tenant_id=user.tenant_id, customer_id=customer_id, **data.model_dump())
    db.add(pref)
    try:
        db.commit(); db.refresh(pref)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una preferencia principal para este cliente, sucursal y servicio")
    return {"id": pref.id, "customer_id": pref.customer_id, "branch_id": pref.branch_id,
            "staff_id": pref.staff_id, "service_id": pref.service_id, "is_primary": pref.is_primary}


@app.get("/customers/{customer_id}/history")
def customer_service_history(customer_id: int, limit: int = 100,
        user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter_by(id=customer_id, tenant_id=user.tenant_id).first()
    if not customer or not _customer_visible(db, user, customer): raise HTTPException(404, "Cliente no encontrado")
    allowed = accessible_branch_ids(db, user)
    q = db.query(ServiceHistory).filter_by(tenant_id=user.tenant_id, customer_id=customer_id)
    if allowed is not None: q = q.filter(ServiceHistory.branch_id.in_(allowed))
    return [{"service": x.service_name_snapshot, "professional": x.staff_name_snapshot,
             "starts_at": x.starts_at, "completed_at": x.completed_at, "branch_id": x.branch_id}
            for x in q.order_by(ServiceHistory.starts_at.desc()).limit(min(max(limit, 1), 500)).all()]


@app.post("/appointments/{appointment_id}/complete")
def complete_appointment(appointment_id: int,
        user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter_by(id=appointment_id, tenant_id=user.tenant_id).with_for_update().first()
    if not appointment: raise HTTPException(404, "Reserva no encontrada")
    assert_branch_access(db, user, appointment.branch_id)
    if appointment.status == "COMPLETED": return {"status": "COMPLETED", "appointment_id": appointment.id}
    if appointment.status != "CONFIRMED": raise HTTPException(409, "Solo se puede completar una cita confirmada")
    service = db.query(Service).filter_by(id=appointment.service_id, tenant_id=user.tenant_id).first()
    staff = db.query(Staff).filter_by(id=appointment.staff_id, tenant_id=user.tenant_id).first() if appointment.staff_id else None
    appointment.status = "COMPLETED"
    db.add(ServiceHistory(tenant_id=user.tenant_id, appointment_id=appointment.id,
        customer_id=appointment.customer_id, branch_id=appointment.branch_id, service_id=appointment.service_id,
        service_name_snapshot=service.name if service else "Servicio", staff_id=appointment.staff_id,
        staff_name_snapshot=staff.name if staff else None, starts_at=appointment.starts_at))
    audit(db, user, "appointment.completed", "appointment", appointment.id)
    db.commit()
    return {"status": "COMPLETED", "appointment_id": appointment.id}



@app.get("/")
def root():
    return {"service": "AgendaVoice AI", "version": "5.0.3", "docs": "/docs"}
