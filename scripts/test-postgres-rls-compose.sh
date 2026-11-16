#!/usr/bin/env bash
set -euo pipefail

# Prueba destructiva solo para una base local dedicada. Crea agendavoice_test
# si no existe y genera/elimina tenants temporales dentro de esa base.
docker compose up -d db redis
ready=false
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U postgres -d agendavoice >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done
if [[ "$ready" != true ]]; then
  echo "ERROR: PostgreSQL no estuvo listo dentro de 60 segundos." >&2
  exit 1
fi
# En volúmenes creados con R4.1, init.sql no vuelve a ejecutarse.
docker compose exec -T db psql -U postgres -d agendavoice -c \
  "CREATE EXTENSION IF NOT EXISTS btree_gist"
docker compose build api

if ! docker compose exec -T db psql -U postgres -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='agendavoice_test'" | grep -q 1; then
  docker compose exec -T db psql -U postgres -d postgres -c "CREATE DATABASE agendavoice_test"
fi
docker compose exec -T db psql -U postgres -d postgres -c \
  "GRANT CONNECT ON DATABASE agendavoice_test TO agendavoice_migrator, agendavoice_app"
docker compose exec -T db psql -U postgres -d agendavoice_test -c \
  "CREATE EXTENSION IF NOT EXISTS btree_gist; GRANT USAGE, CREATE ON SCHEMA public TO agendavoice_migrator; GRANT USAGE ON SCHEMA public TO agendavoice_app; ALTER DEFAULT PRIVILEGES FOR ROLE agendavoice_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agendavoice_app; ALTER DEFAULT PRIVILEGES FOR ROLE agendavoice_migrator IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO agendavoice_app"

MIGRATOR_URL='postgresql+psycopg://agendavoice_migrator:local_migrator_change_me@db:5432/agendavoice_test'
APP_URL='postgresql+psycopg://agendavoice_app:local_app_change_me@db:5432/agendavoice_test'

docker compose run --rm -e MIGRATION_DATABASE_URL="$MIGRATOR_URL" api \
  sh -lc 'alembic upgrade head'
docker compose run --rm -e TEST_DATABASE_URL="$APP_URL" api \
  sh -lc 'pytest -q tests/integration/test_postgres_rls.py tests/integration/test_postgres_scheduling_concurrency.py'
