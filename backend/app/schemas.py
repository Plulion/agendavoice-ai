from datetime import datetime, timezone, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator, model_validator

Role = Literal["SUPER_ADMIN", "TENANT_ADMIN", "BRANCH_MANAGER", "OPERATOR", "READ_ONLY"]

class RegisterIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    admin_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20)
class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
class UserCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Literal["BRANCH_MANAGER", "OPERATOR", "READ_ONLY"]
    branch_ids: list[int] = Field(min_length=1, max_length=100)
class BranchIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    address: str | None = None
    phone: str | None = None
    timezone: str = "America/Santiago"

    @field_validator("timezone")
    @classmethod
    def valid_iana_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Debe ser una zona horaria IANA válida")
        return value
class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    duration_minutes: int = Field(gt=0, le=600)
    buffer_minutes: int = Field(default=0, ge=0, le=180)
    price: float = Field(ge=0)
    currency: str = Field(default="CLP", pattern="^(CLP|USD|EUR)$")
class StaffIn(BaseModel):
    branch_id: int
    name: str = Field(min_length=2, max_length=120)
    specialties: str = ""
class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=40)
    email: EmailStr | None = None
    # Optional. For single-branch operators, defaults to their assigned branch automatically.
    branch_id: int | None = None
class PhoneResolveIn(BaseModel):
    branch_id: int
    phone: str = Field(min_length=6, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None


class AppointmentIn(BaseModel):
    branch_id: int
    customer_id: int | None = None
    customer_phone: str | None = Field(default=None, min_length=6, max_length=40)
    customer_name: str | None = Field(default=None, min_length=2, max_length=160)
    customer_email: EmailStr | None = None
    service_id: int
    staff_id: int | None = None
    resource_id: int | None = None
    starts_at: datetime
    @field_validator("starts_at")
    @classmethod
    def normalize_datetime(cls, v):
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("La fecha debe incluir zona horaria ISO-8601")
        return v.astimezone(timezone.utc)
    @model_validator(mode="after")
    def require_bookable_resource(self):
        if self.staff_id is None and self.resource_id is None:
            raise ValueError("La reserva debe asignar un profesional o un recurso")
        if self.customer_id is None and not self.customer_phone:
            raise ValueError("Debe indicar customer_id o customer_phone para identificar al cliente")
        return self
class AppointmentOut(BaseModel):
    id: int
    branch_id: int
    customer_id: int
    service_id: int
    staff_id: int | None
    resource_id: int | None
    starts_at: datetime
    ends_at: datetime
    status: str
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ResourceIn(BaseModel):
    branch_id: int
    name: str = Field(min_length=2, max_length=120)
    resource_type: str = Field(default="CHAIR", min_length=2, max_length=40)


class WeeklyHoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="Monday=0 ... Sunday=6")
    is_closed: bool = False
    opens_at: time | None = None
    closes_at: time | None = None

    @field_validator("opens_at", "closes_at")
    @classmethod
    def local_time_must_be_naive(cls, value):
        if value is not None and value.tzinfo is not None:
            raise ValueError("Los horarios semanales son horas locales sin offset")
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if self.is_closed:
            if self.opens_at is not None or self.closes_at is not None:
                raise ValueError("Un día cerrado no debe incluir horas")
        elif self.opens_at is None or self.closes_at is None or self.closes_at <= self.opens_at:
            raise ValueError("Un día abierto requiere apertura y cierre, y el cierre debe ser posterior")
        return self


class WeeklyBreakIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time

    @field_validator("starts_at", "ends_at")
    @classmethod
    def local_break_time_must_be_naive(cls, value):
        if value.tzinfo is not None:
            raise ValueError("Las pausas usan horas locales sin offset")
        return value

    @model_validator(mode="after")
    def validate_break(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("El fin de la pausa debe ser posterior al inicio")
        return self


class ScheduleConfigIn(BaseModel):
    hours: list[WeeklyHoursIn] = Field(min_length=7, max_length=7)
    breaks: list[WeeklyBreakIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_week(self):
        days = [item.weekday for item in self.hours]
        if sorted(days) != list(range(7)):
            raise ValueError("Debe definir exactamente una entrada para cada día de la semana")
        by_day = {item.weekday: item for item in self.hours}
        grouped = {}
        for pause in self.breaks:
            window = by_day[pause.weekday]
            if window.is_closed or pause.starts_at < window.opens_at or pause.ends_at > window.closes_at:
                raise ValueError("Cada pausa debe estar dentro del horario abierto de ese día")
            grouped.setdefault(pause.weekday, []).append(pause)
        for weekday, pauses in grouped.items():
            pauses.sort(key=lambda item: item.starts_at)
            if any(current.starts_at < previous.ends_at for previous, current in zip(pauses, pauses[1:])):
                raise ValueError(f"Las pausas del día {weekday} no pueden solaparse")
        return self


class AppointmentCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class OmnichannelTurnIn(BaseModel):
    branch_id: int
    channel: Literal["VOICE", "WHATSAPP"] = "VOICE"
    sender_phone: str = Field(min_length=6, max_length=40)
    sender_name: str = Field(default="Cliente", min_length=2, max_length=160)
    message: str = Field(min_length=1, max_length=1000)
    service_id: int | None = None
    staff_id: int | None = None
    resource_id: int | None = None
    starts_at: datetime | None = None
