# Changelog

## 5.0.3 — Cross-branch privacy hardening, email TLS/local time, rate limiting & omnichannel fixes

### Security & Privacy Fixes
- **A1:** `POST /customers/resolve-phone` no longer leaks `id` or `name` for customers belonging exclusively to another branch; returns a sanitized cross-branch notice instead.
- **A2:** `POST /appointments` always delivers confirmation links for existing customers strictly to their stored DB email (preventing email hijacking via `customer_email`) and omits `customer.name` in cross-branch confirmation emails.
- **A4:** Added fixed-window rate limits to `POST /appointments` and `POST /appointments/{id}/resend-confirmation` (30 bookings/hour per user; 5 confirmation emails/hour per recipient address).
- **N1:** Enforced strict `^[A-Za-z0-9_-]{32,200}$` token regex validation on public confirmation GET/POST routes, added preview rate limiting, and replaced string interpolation with `json.dumps(token)`.
- **B4:** Masked raw Ollama exception strings behind a generic HTTP 503 message in `POST /ai/local/chat` (logging details server-side).

### Functional & Operational Improvements
- **M3:** Confirmation emails now display appointment date/time formatted in the branch's local IANA timezone (`America/Santiago`) instead of raw UTC.
- **M4:** Added `POST /appointments/{appointment_id}/resend-confirmation` to rotate tokens and resend confirmation emails for `PENDING` bookings.
- **M6:** Added optional `SMTP_USE_TLS`, `SMTP_USERNAME`, and `SMTP_PASSWORD` support (`STARTTLS` + `SMTP.login`) while keeping Mailpit defaults for local development.
- **N2 / N3 / N4:** Omnichannel turns now extract emails from free-text replies via regex, prompt for full name instead of creating new customers named `"Cliente"`, and query both normalized and legacy raw phone formats.
- **Consistency:** Aligned version metadata (`5.0.3`) across `VERSION`, FastAPI, `frontend/package.json`, `frontend/src/App.tsx`, and `docs/index.html`; ensured 100% English documentation in `docs/` and zero `.pyc` cache files.


## 5.0.2 — R5.0.0 audit corrections

### Fixed
- Corrected all four composite foreign-key targets in the waitlist migration.
- Fixed duplicate `customer_id` keyword construction in `POST /waitlist`.
- Added optional email capture to omnichannel booking; new customers without a stored/provided email are asked for it before a booking is created.
- Changed omnichannel booking wording to accurately describe `PENDING` status and email confirmation.
- Persisted expired pending-appointment releases when availability is queried.
- Changed email confirmation to a safe GET landing page plus explicit, rate-limited POST action; public confirmation is now audited.
- Loaded PostgreSQL RLS integration-test credentials from `.env`, matching Compose configuration.
- Flushed updates to existing primary professional preferences before inserting the replacement.
- Normalized customer phone numbers on creation.
- Restricted tenant-global customer profile edits to tenant administrators and made profile updates partial, preserving omitted fields.
- Updated API/package version metadata and added regression tests.

### Validation
- Python compileall: passed.
- Pytest: 59 passed, 3 skipped.
- Shell syntax check for `scripts/test-postgres-rls-compose.sh`: passed.
- Docker/PostgreSQL migration and integration execution: not run in this environment; Docker CLI is unavailable.
- Frontend npm build: not run; dependencies were not available in the local npm cache.

**Status:** corrected local validation candidate; not certified for Docker/GitHub release until the outstanding Docker/PostgreSQL and frontend checks pass.


## 5.0.0 — Customer relationship and local-first confirmation foundation

### Added
- Customer first/last names and optional Chilean RUT with checksum validation and tenant-scoped uniqueness.
- Versioned data-processing and marketing consent records.
- Preferred professional records by customer, branch and optional service.
- Email-confirmed appointment lifecycle (`PENDING` to `CONFIRMED`) with expiring random token, SHA-256 storage, HTML confirmation button and local Mailpit SMTP.
- Email outbox delivery status; raw confirmation token is not persisted in the outbox.
- Service-history snapshot when a confirmed appointment is completed.
- Basic branch/service waitlist records.
- Local Ollama provider adapter and isolated `/ai/local/chat` smoke-test endpoint (no database tools).
- FORCE RLS policies for new tenant-owned tables; Alembic revision `0006_r5_customer_confirmation_history`.
- R5 master specification, API reference, Mac setup, local test plan and internal release audit.

### Notes
- R5.0.0 is a local development foundation, not a production-ready release. Full conversational onboarding, automatic preference application, automatic waitlist matching, reminders, multi-service booking, product sales and the complete admin UI remain on the roadmap.
- R4.3.0 code, migrations and tests are retained.

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
