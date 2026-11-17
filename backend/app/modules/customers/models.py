from sqlalchemy import String, Integer, ForeignKey, DateTime, func, UniqueConstraint, ForeignKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    # Origin branch where the customer was registered. Allows that branch to view the customer before their first booking.
    home_branch_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_customer_tenant_phone"),
                      UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id"),
                      ForeignKeyConstraint(["tenant_id", "home_branch_id"], ["branches.tenant_id", "branches.id"], name="fk_customer_home_branch"),
                      Index("ix_customers_tenant_home_branch", "tenant_id", "home_branch_id"))
