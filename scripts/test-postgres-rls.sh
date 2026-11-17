#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
  echo "ERROR: set TEST_DATABASE_URL pointing to an already-migrated PostgreSQL test database." >&2
  exit 2
fi
cd "$(dirname "$0")/../backend"
pytest -q tests/integration/test_postgres_rls.py tests/integration/test_postgres_scheduling_concurrency.py
