> **Histórico:** este documento registra la auditoría de la primera versión R5.0.0 y no debe interpretarse como verificación de R5.0.2. Para las correcciones y pruebas de la versión actual, consulte `R5_0_2_CORRECTION_REPORT.md`.

# R5.0.3 Internal Release Audit

## Source package

Based on the uploaded `agendavoice-ai-R4.3.0-EN.zip`. Existing R4.3.0 modules, migrations, tests, Docker setup, frontend and documentation were retained and incremented.

## Implemented and reviewed in this package

- Customer first/last name and optional Chilean RUT fields; legacy `name` remains.
- RUT normalization and modulus-11 validation utility.
- Consent records with consent type, decision, policy version and source.
- Professional preferences scoped by tenant/customer/branch and optional service.
- Appointment confirmation token storage as SHA-256 hash, expiry, and public confirmation endpoint.
- Appointment creation now creates `PENDING` status and queues an email; successful delivery via configured SMTP is marked `SENT`, failures remain `FAILED`.
- Local Mailpit service added to Compose.
- Expired pending appointments are released when a new booking or availability lookup is performed.
- Completed appointment endpoint creates a service-history snapshot.
- Basic waitlist create/list endpoints.
- Ollama local chat adapter; no tools or database data are exposed to the model.
- RLS policies added to new tenant-owned tables.
- Alembic environment no longer assumes logging sections exist in the minimal `alembic.ini`.

## Automated checks executed in the build environment

- Python compileall: passed.
- Docker Compose YAML parse and PostgreSQL init shell syntax check: passed.
- Docker build/Compose runtime: not executed because the build environment does not contain the Docker CLI.
- Pytest: **53 passed, 3 skipped**. The 3 skipped tests are PostgreSQL integration tests requiring a separate migrated test database.
- Alembic revision graph: passed; `0006_r5_customer_confirmation_history` is the head after `0005_r422_customer_home_branch`.
- FastAPI application import and route registration: passed using test-only stubs for Python packages absent from this build container; 25 SQLAlchemy tables registered and R5 routes found.
- Main application could not be run end-to-end in this build container because several pinned runtime packages (including redis, psycopg, python-jose and python-slugify) are not installed and internet access is unavailable to install them. The Docker image installs `requirements.txt` at build time.
- PostgreSQL migration execution, RLS behavior, email delivery through a running Mailpit container, Docker build and browser UI were **not** executed in this environment.

## Known limitations / blockers before production

1. Full new-vs-returning customer conversational workflow is not wired into the AI agent.
2. Professional preferences are persisted but are not automatically applied by the booking conversation.
3. Waitlist is a stored queue; automatic matching and customer notification are not implemented.
4. Confirmation email includes both plain text and an HTML button (with branch local timezone in R5.0.3) and a rate-limited resend endpoint (`POST /appointments/{id}/resend-confirmation`); branded custom per-tenant templates remain on the roadmap.
5. Outbox failed records are retained, but a robust background retry worker and delivery-event ingestion remain.
6. Expired pending bookings are cleaned when booking/availability is requested; a scheduled cleanup worker is still needed.
7. Customer history access is protected by tenant/branch visibility for authenticated staff; customer self-service identity verification is not yet implemented.
8. No multi-service appointment orchestration, automated reminder scheduler, no-show workflow, products/stock, checkout, payments, loyalty, full admin frontend or production telephony.
9. PostgreSQL RLS and concurrency tests must be run against a fresh disposable PostgreSQL database before accepting the release.
10. The R5.0.0 package is a development foundation, not production-ready or a fully finished three-month MVP.

## Security review notes

- Confirmation tokens are 32-byte URL-safe random values validated against `^[A-Za-z0-9_-]{32,200}$`; only SHA-256 digests are stored in the confirmation table, and confirmation requires an explicit POST action.
- Existing customers always receive confirmation emails strictly at their stored DB email address (no cross-branch email redirection), and `POST /customers/resolve-phone` hides `id`/`name` for other-branch records.
- Raw token is not persisted in email outbox body; it is passed to SMTP at send time.
- Public confirmation lookup uses a dedicated RLS SELECT policy matching the hash placed in a transaction-local setting, then switches to the matching tenant context before loading/updating appointment data.
- New tenant tables use FORCE ROW LEVEL SECURITY and tenant-isolation policies.
- Email is required to create an appointment in R5 because the requested workflow requires explicit email confirmation.
- The app still uses development-only local passwords in Compose defaults; replace them before any network exposure.

## Release verdict

**Suitable for controlled local development and further integration. Not cleared for production.** Complete the R5.1 workflow items and execute PostgreSQL integration tests before calling the salon MVP feature-complete.
