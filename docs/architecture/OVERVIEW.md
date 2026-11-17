# AgendaVoice AI — Architecture Overview (R4.3.0)

## Architectural Principles

AgendaVoice AI is a multi-tenant, multi-branch B2B scheduling platform. The shared core manages identity, tenant isolation, branches, role-based permissions, customer scope, service catalogs, weekly schedules, concurrency locks, omnichannel AI orchestration, and append-only audit logs.

## Layered Design

- **API Layer:** FastAPI with JWT authentication, Redis fixed-window rate limiting, and strict branch-level RBAC (`assert_branch_access`).
- **Domain Modules:** `identity`, `tenants`, `branches`, `customers`, `catalog`, `scheduling`, `subscriptions`, `audit`, plus `integrations/gemini` and `integrations/twilio`.
- **Persistence & Concurrency:** SQLAlchemy 2.0, PostgreSQL 16, and Alembic. Appointments are stored as UTC `TIMESTAMPTZ` ranges (`[starts_at, ends_at)`), while recurring weekly schedules use each branch's local IANA timezone (`America/Santiago`).
- **Two-Ring Isolation:**
  - **Ring 1 (Inter-Tenant):** PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY` bound to `app.tenant_id` across all tables (including `tenants`).
  - **Ring 2 (Intra-Tenant Branch Scope):** `user_branch_access` filtering for schedules, staff, resources, appointments, and customer lists, paired with exact-phone **Blind Upsert** for frictionless cross-branch telephone/WhatsApp booking.
- **Double-Booking Prevention:** Transaction-scoped `pg_advisory_xact_lock` combined with PostgreSQL `EXCLUDE USING gist` (`btree_gist`) constraints over active appointments.

## Authentication & Transaction Context Lifecycle

1. Registration (`POST /auth/register`) reserves a sequence ID, sets `app.tenant_id`, and atomically creates the tenant, `TENANT_ADMIN` user, `auth_identities` lookup row, trial subscription, and rotating refresh session.
2. Login (`POST /auth/login`) queries `auth_identities` by normalized email to obtain `(user_id, tenant_id)`, activates `app.tenant_id` under RLS, and verifies the password hash against `users`.
3. `Session.info["tenant_id"]` stores the active tenant for the HTTP request lifecycle, while a SQLAlchemy `Session.after_begin` listener re-executes `SELECT set_config('app.tenant_id', ..., true)` at the start of every transaction so `COMMIT` calls never drop RLS context.
