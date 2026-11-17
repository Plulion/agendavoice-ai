from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, func, ForeignKeyConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, nullable=False)
    staff_id: Mapped[int | None] = mapped_column(Integer)
    preferred_from: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    preferred_to: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="WAITING")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE", name="fk_waitlist_branch"), ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE", name="fk_waitlist_customer"), ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], name="fk_waitlist_service"), ForeignKeyConstraint(["tenant_id", "branch_id", "staff_id"], ["staff.tenant_id", "staff.branch_id", "staff.id"], name="fk_waitlist_staff"), Index("ix_waitlist_matching", "tenant_id", "branch_id", "service_id", "status", "preferred_from", "preferred_to"), CheckConstraint("preferred_to > preferred_from", name="ck_waitlist_range"), CheckConstraint("status IN ('WAITING','OFFERED','BOOKED','CANCELLED')", name="ck_waitlist_status"))
