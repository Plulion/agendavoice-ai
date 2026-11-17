# AgendaVoice AI R5.0.3 — Local-first foundation

**Universal multi-tenant appointment and customer-engagement platform. First vertical: salons / barber shops.**

R5.0.3 builds on the R4.3.0 codebase and adds customer profiles (first/last name and Chilean RUT), recorded consent, preferred professionals, service history, email appointment confirmation, a basic waitlist and a local Ollama adapter. The existing tenant isolation, branch scoping, scheduling, resource availability and audit foundation are retained.

> **Release status: local validation candidate. Docker/PostgreSQL release checks remain pending; not production-ready.** This ZIP is a corrected R5 local validation candidate, not a claim that every feature in the master roadmap is finished. See `docs/R5_MASTER_SPEC.md` and `docs/R5_RELEASE_AUDIT.md` for implemented vs pending scope.

## 1. What is implemented in R5.0.3

- Customer registration accepts first name, last name, phone, email and optional validated Chilean RUT; the legacy `name` field remains compatible.
- Customer profile updates and consent history (`DATA_PROCESSING`, `EMAIL_MARKETING`).
- Customer preferences for a professional by branch and optionally by service.
- Appointment creation changes to `PENDING` until a secure email confirmation link is used.
- Confirmation tokens are random, time-limited and stored as SHA-256 hashes. Expired unconfirmed bookings are released when booking or availability is queried.
- Local SMTP sink via Mailpit; inspect messages at http://localhost:8025. No paid email provider is required for local testing.
- Completed appointments create an immutable service-history snapshot containing service and professional names, date/time and branch.
- Basic waitlist create/list endpoints.
- Local Ollama chat adapter behind a provider boundary. It cannot access the database or execute business tools.
- New RLS-protected tables for all R5 customer/workflow records.

## 2. Not yet implemented (do not assume otherwise)

- Full conversational onboarding that asks “new or returning customer” and automatically looks up customer history/preferences in the AI dialogue.
- Automatic application of the preferred professional during every booking (preference is stored and queryable, but booking selection workflow still needs integration).
- Automatic waitlist matching and outreach after a cancellation.
- Full rebooking/rescheduling flow, automatic reminder scheduler, no-show policy automation and multi-service/multi-professional booking.
- Product variants, stock, cart, checkout, gift cards, loyalty points and payment processing.
- Complete salon admin dashboard and customer self-service portal.
- Production telephony, WhatsApp/SMS, Gemini cloud integration and AWS deployment. These remain deliberately disabled/deferred.

## 3. Requirements

- macOS with Docker Desktop and Docker Compose v2.
- Python 3.11+ if running backend tools outside Docker.
- Node 20+ only if running the frontend outside Docker.
- Ollama is optional. Core API and booking tests do not require a language model.

## 4. Run locally on a Mac

```bash
cd agendavoice-ai-R5.0.3
cp .env.example .env
```

Change `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` and `MIGRATOR_DB_PASSWORD` in `.env` before starting. Use alphanumeric values to avoid URL-encoding issues in the database connection strings. Defaults are development-only and must never be used on an exposed host.

```bash
docker compose up --build -d
docker compose ps
```

Services:

- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- Frontend: http://localhost:5173
- Mailpit inbox: http://localhost:8025
- PostgreSQL: localhost:5432
- Redis: localhost:6379

The API container runs Alembic migrations automatically before Uvicorn. Check:

```bash
curl http://localhost:8000/health
```

Stop services:

```bash
docker compose down
```

Stop and delete the local database volume (DESTRUCTIVE; removes local test data):

```bash
docker compose down -v
```

## 5. Optional local AI with Ollama (no Gemini key)

Install Ollama natively on the Mac, then:

```bash
ollama pull qwen2.5:3b
ollama serve
```

The Docker API reaches the Mac host through `host.docker.internal:11434`. `.env.example` sets this as `OLLAMA_BASE_URL`. If the API is run directly on macOS rather than in Docker, set it to `http://localhost:11434`.

After logging in and obtaining an access token, test `POST /ai/local/chat` with:

```json
{"message":"Saluda a una clienta y pregúntale qué servicio necesita."}
```

This endpoint is a local model smoke test only. The model does not receive customer records and cannot create bookings. Business actions must later be implemented as validated backend tools with tenant and permission checks.

## 6. Test suite

Inside the backend directory:

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

The three PostgreSQL integration tests require a migrated disposable PostgreSQL database and `TEST_DATABASE_URL`; they are skipped otherwise. Unit tests do not prove PostgreSQL RLS/concurrency behavior.

## 7. GitHub

After local validation and before publishing, review `.env`, remove secrets and local data, then:

```bash
git init
git add .
git commit -m "AgendaVoice AI R5.0.3 local-first foundation"
git branch -M main
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

Replace the repository URL with your own. Do not commit `.env`, customer data, database dumps, or real credentials.

## 8. Documents

- `docs/R5_MASTER_SPEC.md`: consolidated functional scope and product decisions.
- `docs/R5_0_3_SECURITY_HARDENING.md`: R5.0.3 security hardening and audit remediation report.
- `docs/R5_RELEASE_AUDIT.md`: implementation audit and known limitations.
- `docs/LOCAL_SETUP_MAC.md`: Mac setup and local troubleshooting.
- `docs/LOCAL_TEST_PLAN.md`: manual and automated test plan.
- `docs/architecture/R5_COMPONENTS.mmd`: component architecture.
- `docs/uml/R5_ERD.mmd`: core data model.
- `docs/api/ENDPOINTS_R5.md`: new R5 endpoints.
