# Relational Data Model

## Core Entities

- `tenants`: Root company records protected by Row-Level Security (`id = current_setting('app.tenant_id')`).
- `users`: Platform users, role assignments (`SUPER_ADMIN`, `TENANT_ADMIN`, `BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`), and tenant membership.
- `auth_identities`: Minimal global lookup index (`email`, `user_id`, `tenant_id`) used exclusively to resolve the tenant prior to login without storing password hashes or business data.
- `refresh_sessions`: Hashed JTI tokens, expiration timestamps, and revocation state for rotating refresh sessions.
- `user_branch_access`: Explicit mapping of branch-scoped users to their authorized `branch_id`s.
- `branches`: Company branches including address, phone number, and validated IANA timezone (`America/Santiago` by default).
- `customers`: Company-level customer records (`uq_customer_tenant_phone`) with `home_branch_id` tracking the origin branch.
- `services`: Service catalog including `duration_minutes`, `buffer_minutes`, `price`, and `currency`.
- `staff`: Branch professionals and specialties.
- `resources`: Physical bookable assets per branch (e.g., chairs, rooms, vehicles, bays).
- `appointments`: Confirmed, pending, or cancelled bookings stored as UTC `TIMESTAMPTZ` intervals (`[starts_at, ends_at)`).
- `subscriptions`: Tenant subscription plan and lifecycle state.
- `audit_logs`: Append-only administrative and security audit trail (`REVOKE UPDATE, DELETE` enforced for the runtime DB role).

---

## Schedule & Break Tables (R4.2+)

- `branch_hours` / `branch_breaks`: 7-day local opening windows and breaks per branch.
- `staff_hours` / `staff_breaks`: Optional 7-day schedule overrides and breaks per professional (inherits from branch if unconfigured).
- `resource_hours` / `resource_breaks`: Optional 7-day schedule overrides and breaks per physical resource (inherits from branch if unconfigured).

---

## Multi-Tenant & Multi-Branch Referential Integrity

All tenant-scoped tables enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Furthermore, references from `appointments` and schedule tables to `staff` and `resources` use **three-column composite foreign keys** `(tenant_id, branch_id, entity_id)`, guaranteeing at the PostgreSQL engine level that a booking in Branch A can never reference a staff member or physical resource belonging to Branch B.
