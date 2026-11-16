from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, func, CheckConstraint, UniqueConstraint, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialties: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_staff_tenant_id"),
        UniqueConstraint("tenant_id", "branch_id", "id", name="uq_staff_tenant_branch_id"),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_staff_tenant_branch"))

class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, default="CHAIR")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_resources_tenant_id"),
        UniqueConstraint("tenant_id", "branch_id", "id", name="uq_resources_tenant_branch_id"),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_resources_tenant_branch"))

class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, nullable=False)
    staff_id: Mapped[int | None] = mapped_column(Integer)
    resource_id: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CONFIRMED")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_appointment_positive_range"),
        CheckConstraint("status IN ('PENDING','CONFIRMED','CANCELLED','COMPLETED','NO_SHOW')", name="ck_appointment_status"),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], name="fk_appointment_tenant_branch"),
        ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], name="fk_appointment_tenant_customer"),
        ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], name="fk_appointment_tenant_service"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], name="fk_appointment_tenant_branch_staff"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "resource_id"], ["resources.tenant_id", "resources.branch_id", "resources.id"], name="fk_appointment_tenant_branch_resource"),
    )

# Horarios semanales expresados en la hora local de la sucursal.
from sqlalchemy import Time, Index

class BranchHours(Base):
    __tablename__ = "branch_hours"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # lunes=0 ... domingo=6
    opens_at: Mapped[object | None] = mapped_column(Time)
    closes_at: Mapped[object | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "branch_id", "weekday", name="uq_branch_hours_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_branch_hours_weekday"),
        CheckConstraint("(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR (NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)", name="ck_branch_hours_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_branch_hours_branch"),
        Index("ix_branch_hours_tenant_branch_day", "tenant_id", "branch_id", "weekday"),
    )

class BranchBreak(Base):
    __tablename__ = "branch_breaks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[object] = mapped_column(Time, nullable=False)
    ends_at: Mapped[object] = mapped_column(Time, nullable=False)
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_branch_break_weekday"),
        CheckConstraint("ends_at > starts_at", name="ck_branch_break_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_branch_breaks_branch"),
        Index("ix_branch_breaks_tenant_branch_day", "tenant_id", "branch_id", "weekday"),
    )

class StaffHours(Base):
    __tablename__ = "staff_hours"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    staff_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[object | None] = mapped_column(Time)
    closes_at: Mapped[object | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "staff_id", "weekday", name="uq_staff_hours_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_staff_hours_weekday"),
        CheckConstraint("(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR (NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)", name="ck_staff_hours_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], ondelete="CASCADE", name="fk_staff_hours_tenant_branch_staff"),
        Index("ix_staff_hours_tenant_branch_staff_day", "tenant_id", "branch_id", "staff_id", "weekday"),
    )

class StaffBreak(Base):
    __tablename__ = "staff_breaks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    staff_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[object] = mapped_column(Time, nullable=False)
    ends_at: Mapped[object] = mapped_column(Time, nullable=False)
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_staff_break_weekday"),
        CheckConstraint("ends_at > starts_at", name="ck_staff_break_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], ondelete="CASCADE", name="fk_staff_breaks_tenant_branch_staff"),
        Index("ix_staff_breaks_tenant_branch_staff_day", "tenant_id", "branch_id", "staff_id", "weekday"),
    )

class ResourceHours(Base):
    __tablename__ = "resource_hours"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[object | None] = mapped_column(Time)
    closes_at: Mapped[object | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_id", "weekday", name="uq_resource_hours_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_resource_hours_weekday"),
        CheckConstraint("(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR (NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)", name="ck_resource_hours_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "resource_id"], ["resources.tenant_id", "resources.branch_id", "resources.id"], ondelete="CASCADE", name="fk_resource_hours_tenant_branch_resource"),
        Index("ix_resource_hours_tenant_branch_resource_day", "tenant_id", "branch_id", "resource_id", "weekday"),
    )

class ResourceBreak(Base):
    __tablename__ = "resource_breaks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[object] = mapped_column(Time, nullable=False)
    ends_at: Mapped[object] = mapped_column(Time, nullable=False)
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_resource_break_weekday"),
        CheckConstraint("ends_at > starts_at", name="ck_resource_break_range"),
        ForeignKeyConstraint(["tenant_id", "branch_id", "resource_id"], ["resources.tenant_id", "resources.branch_id", "resources.id"], ondelete="CASCADE", name="fk_resource_breaks_tenant_branch_resource"),
        Index("ix_resource_breaks_tenant_branch_resource_day", "tenant_id", "branch_id", "resource_id", "weekday"),
    )
