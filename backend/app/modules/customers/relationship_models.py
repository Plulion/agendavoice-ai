from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, JSON, func, UniqueConstraint, ForeignKeyConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class CustomerConsent(Base):
    __tablename__ = "customer_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    consent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="WEB")
    recorded_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_customer_consent_customer"),)

class CustomerStaffPreference(Base):
    __tablename__ = "customer_staff_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    staff_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[int | None] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_customer_staff_pref_customer"), ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], ondelete="CASCADE", name="fk_customer_staff_pref_staff"), ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], name="fk_customer_staff_pref_service"), Index("ix_customer_staff_pref_lookup", "tenant_id", "customer_id", "branch_id"), Index("uq_customer_staff_pref_primary_scope", "tenant_id", "customer_id", "branch_id", text("COALESCE(service_id, 0)"), unique=True, postgresql_where=text("is_primary")))

class ServiceHistory(Base):
    __tablename__ = "service_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    staff_id: Mapped[int | None] = mapped_column(Integer)
    staff_name_snapshot: Mapped[str | None] = mapped_column(String(120))
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"], ondelete="CASCADE", name="fk_service_history_appointment"), ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_service_history_customer"), Index("ix_service_history_customer_date", "tenant_id", "customer_id", "starts_at"))
