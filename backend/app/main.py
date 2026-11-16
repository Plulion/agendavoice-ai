from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, Depends, HTTPException, Request
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
from app.modules.catalog.models import Service
from app.modules.scheduling.models import (Staff, Resource, Appointment, BranchHours, BranchBreak, StaffHours, StaffBreak, ResourceHours, ResourceBreak)
from app.modules.subscriptions.models import Subscription
from app.modules.audit.models import AuditLog
from app.modules.scheduling.availability import WeeklyWindow, WeeklyBreak, interval_fits_schedule, local_slot_to_utc, iter_local_slots
from app.schemas import (RegisterIn, LoginIn, RefreshIn, TokenOut, UserCreateIn,
    BranchIn, ServiceIn, StaffIn, CustomerIn, AppointmentIn, AppointmentOut,
    ResourceIn, ScheduleConfigIn, AppointmentCancelIn, PhoneResolveIn, OmnichannelTurnIn)
from app.modules.customers.visibility import normalize_phone, sanitize_cross_branch_customer
from app.integrations.gemini.agent import run_branch_conversation_turn

app = FastAPI(title="AgendaVoice AI API", version="4.3.0", description="Motor universal de agenda multiempresa")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

# Límites por IP/correo en endpoints de autenticación. Redis comparte el contador entre procesos.
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
    """Filtra clientes por acceso: admins ven todos; el resto, los de sus sucursales."""
    allowed = accessible_branch_ids(db, user)
    if allowed is None:
        return query
    if not allowed:
        return query.filter(false())
    visited = select(Appointment.customer_id).where(
        Appointment.tenant_id == user.tenant_id, Appointment.branch_id.in_(allowed))
    return query.filter(or_(Customer.home_branch_id.in_(allowed), Customer.id.in_(visited)))


def _customer_visible(db, user, customer) -> bool:
    """Misma regla que _customer_scope, para un cliente concreto (ver modules/customers/visibility.py)."""
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
) -> tuple[Customer, bool]:
    """Estándar de industria (Blind Upsert): busca por teléfono exacto dentro del tenant
    o crea el cliente asignándole la sucursal actual como home_branch_id.
    Retorna (customer, was_existing_other_branch).
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
        return existing, was_other

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
    return obj, False


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
        # Reserva primero el ID para poder establecer RLS antes de insertar tenants.
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
    # Este índice contiene únicamente email/user_id/tenant_id. La contraseña y el
    # registro completo se consultan después de establecer el tenant bajo RLS.
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
            # Renovación casi simultánea (otra pestaña): se rechaza sin cerrar sesiones.
            raise HTTPException(401, "Sesión de renovación revocada o expirada")
        # Reuso fuera de la ventana: se asume robo y se cierran todas las sesiones del usuario.
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
        # Mensaje genérico: no confirma datos de otros clientes de la empresa.
        raise HTTPException(409, "El teléfono ya está registrado en la empresa; un administrador debe revisarlo")
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
    """Permite a una sucursal vincular o crear un cliente por su teléfono exacto sin depender del administrador
    y sin exponer el historial de otras sucursales (protegido contra enumeración mediante rate limit).
    """
    enforce_rate_limit(f"resolve-phone:{user.tenant_id}:{user.id}:{client_ip(request)}", 15, 60)
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter_by(id=data.branch_id, tenant_id=user.tenant_id, active=True).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada")
    customer, was_other = _resolve_or_create_customer_by_phone(
        db, user, data.branch_id, data.phone, data.name, str(data.email) if data.email else None
    )
    db.commit()
    db.refresh(customer)
    if was_other:
        return sanitize_cross_branch_customer(customer.id, customer.name, customer.phone)
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


@app.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(data: AppointmentIn, user: User = Depends(require_roles(
        "TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")), db: Session = Depends(get_db)):
    assert_branch_access(db, user, data.branch_id)
    branch = db.query(Branch).filter(Branch.id == data.branch_id,
        Branch.tenant_id == user.tenant_id, Branch.active.is_(True)).first()
    if not branch:
        raise HTTPException(404, "Sucursal, cliente o servicio no encontrado")
    customer = None
    if data.customer_phone:
        # Blind Upsert por teléfono exacto: permite agendar en Sucursal B a un cliente de Sucursal A
        # sin exponer su historial previo ni requerir intervención del administrador.
        customer, _ = _resolve_or_create_customer_by_phone(
            db, user, branch.id, data.customer_phone, data.customer_name,
            str(data.customer_email) if data.customer_email else None,
        )
    elif data.customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == data.customer_id,
            Customer.tenant_id == user.tenant_id).first()
        if customer is not None and not _customer_visible(db, user, customer):
            customer = None  # se responde como no encontrado para no revelar IDs secuenciales de otras sucursales
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

    # Advisory locks ordenados evitan carreras entre solicitudes de la API;
    # las EXCLUDE constraints de PostgreSQL son la garantía final entre procesos.
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
        ends_at=ends, status="CONFIRMED")
    db.add(obj)
    try:
        db.flush()
        audit(db, user, "appointment.created", "appointment", obj.id,
              {"starts_at": starts.isoformat(), "ends_at": ends.isoformat()})
        db.commit()
        db.refresh(obj)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El profesional o recurso acaba de ser reservado por otra solicitud")
    return obj


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
    # Ventana UTC amplia: la medianoche local puede no existir por DST. El solapamiento
    # exacto se valida después para cada intervalo.
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
    user: User = Depends(require_roles("TENANT_ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Ejecuta un turno del agente conversacional (Voz con Gemini o WhatsApp)
    estrictamente aislado a la sucursal indicada.
    """
    assert_branch_access(db, user, data.branch_id)
    tenant = db.query(Tenant).filter_by(id=user.tenant_id, status="ACTIVE").first()
    branch = db.query(Branch).filter_by(id=data.branch_id, tenant_id=user.tenant_id, active=True).first()
    if not tenant or not branch:
        raise HTTPException(404, "Sucursal no encontrada")

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
        appt = create_appointment(
            data=AppointmentIn(
                branch_id=branch.id,
                customer_phone=data.sender_phone,
                customer_name=data.sender_name,
                service_id=data.service_id,
                staff_id=data.staff_id,
                resource_id=data.resource_id,
                starts_at=data.starts_at,
            ),
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


@app.get("/")
def root():
    return {"service": "AgendaVoice AI", "version": "4.3.0", "docs": "/docs"}
