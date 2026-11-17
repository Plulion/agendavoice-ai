# Changelog

## 4.3.0 — Cross-Branch Customer Resolution (Blind Upsert) & Omnichannel Voice/WhatsApp AI

### Added

- **Industry-Standard Cross-Branch Phone Booking (`Blind Upsert` + `POST /customers/resolve-phone`):** Allows any branch to book an existing company customer by phone or WhatsApp using their exact normalized phone number (`+569...`) without requiring administrator intervention and without exposing appointment history or metadata from other branches.
- `POST /appointments` now accepts `customer_phone` + `customer_name` inline during appointment creation.
- **Branch-Scoped Conversational AI Agent (`app/integrations/gemini/agent.py`):** Orchestrator strictly scoped to `branch_id` and `tenant_id` (under PostgreSQL RLS) exposed via `POST /channels/omnichannel/turn`.
- **WhatsApp & Voice Webhook Adapter (`app/integrations/twilio/webhooks.py`):** Sender normalization (`whatsapp:+569...`) and cryptographic `X-Twilio-Signature` (HMAC-SHA1) verification.
- Unit test suite `backend/tests/test_omnichannel_r430.py` (6 new unit tests).
- Interactive English architecture showcase (`docs/index.html`) and complete English documentation across `docs/`.

## 4.2.2 — Branch-Scoped Customer Visibility & Multi-Tab Session Sync

### Added

- Customers now include an origin branch (`home_branch_id`, migration `0005_r422_customer_home_branch`), backfilled from each customer's first appointment branch.
- `POST /customers` accepts an optional `branch_id`. Single-branch operators default to their assigned branch automatically.
- Reference visibility policy documented in `docs/security/CUSTOMER_SCOPE.md` with zero-dependency unit tests.

### Fixed

- `GET /customers` only returns customers visible to the authenticated user (previously visible across the entire tenant).
- `POST /appointments` rejects unauthorized customer IDs with a generic `404` without confirming whether the ID exists in another branch.
- Duplicate phone numbers on `POST /customers` return `409` with a generic message that leaks no existing customer fields.
- Session refresh: a refresh token revoked less than 15 seconds ago is treated as a concurrent multi-tab refresh and rejected without revoking all active user sessions. Reuse after 15 seconds triggers full session revocation.
- Frontend: duplicate tabs adopt rotated tokens via `BroadcastChannel` and serialize refresh calls via `navigator.locks`.

## 4.2.1 — R4.2 Security & DST Audit Hardening

### Fixed

- CORS now allows `PUT` so browser clients can update branch, staff, and resource schedules.
- Fixed-window rate limiting on `/auth/register`, `/auth/login`, and `/auth/refresh` by IP and email using Redis with automatic in-memory fallback.
- Ambiguous (fall-back) and nonexistent (spring-forward) local DST hours are rejected rather than silently resolved (`docs/scheduling/DST_POLICY.md`).
- `audit_logs` is enforced as append-only for the runtime database role (`0004_r421_audit_append_only`).
- Added `backend/.dockerignore` to exclude `.env` and caches from container builds.

## 4.2.0 — Universal Scheduling Engine

### Added

- Weekly opening hours and breaks for branches, staff, and physical resources, protected by PostgreSQL RLS and composite foreign keys.
- IANA timezone validation per branch (`America/Santiago` default) with UTC `timestamptz` appointment storage.
- Availability calculation considering service duration, buffer minutes, schedules, breaks, and active bookings.
- PostgreSQL `EXCLUDE USING gist` (`btree_gist`) constraints plus ordered transaction advisory locks (`pg_advisory_xact_lock`) preventing concurrent double-booking of staff or resources.

## 4.1.0 — SaaS Security Core & Row-Level Security

### Added

- Rotating single-use refresh tokens with hashed JTI storage and explicit logout revocation.
- Minimal global login lookup table (`auth_identities`) eliminating RLS bypass on `users`.
- Role hierarchy (`SUPER_ADMIN`, `TENANT_ADMIN`, `BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`) and branch assignment table (`user_branch_access`).
- `ENABLE` + `FORCE ROW LEVEL SECURITY` across all tenant tables and root `tenants` table, re-applied on every transaction via `Session.after_begin`.
