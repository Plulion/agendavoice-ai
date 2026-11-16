# Importa todos los modelos para que Alembic registre el metadata completo.
from app.modules.tenants.models import Tenant
from app.modules.identity.models import User, AuthIdentity, RefreshSession, UserBranchAccess
from app.modules.branches.models import Branch
from app.modules.customers.models import Customer
from app.modules.catalog.models import Service
from app.modules.scheduling.models import (Staff, Resource, Appointment, BranchHours, BranchBreak, StaffHours, StaffBreak, ResourceHours, ResourceBreak)
from app.modules.subscriptions.models import Subscription
from app.modules.audit.models import AuditLog
