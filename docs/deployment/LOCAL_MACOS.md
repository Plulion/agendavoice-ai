# Local Development & Verification Guide (macOS / Linux)

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- Python 3.10+
- Available local ports: `5432` (PostgreSQL 16), `6379` (Redis 7), `8000` (FastAPI), `5173` (React/Vite)

## 1. Zero-Dependency Unit Tests (No Docker Required)

```bash
cd backend
PYTHONPATH=. python3 tests/test_customer_scope_r422.py
PYTHONPATH=. python3 tests/test_dst_policy_r421.py
PYTHONPATH=. python3 tests/test_omnichannel_r430.py
```

## 2. Full Stack Startup with Docker Compose

```bash
cp .env.example .env
# Edit .env to set a strong 32+ character JWT_SECRET
docker compose up -d --build
```

- **Web Admin Console:** `http://localhost:5173`
- **REST API Base URL:** `http://localhost:8000`
- **Interactive Swagger UI:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`

## 3. Live PostgreSQL 16 RLS & Concurrency Verification

```bash
./scripts/test-postgres-rls-compose.sh
```

This script provisions an isolated `agendavoice_test` database, enables `btree_gist`, runs all Alembic migrations (`0001` through `0005`), and executes `test_postgres_rls.py` and `test_postgres_scheduling_concurrency.py` under the non-superuser runtime role `agendavoice_app`.
