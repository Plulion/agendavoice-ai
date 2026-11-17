# Build Verification Record — R4.2

Build Date: 2026-11-15.

## Verified Checks

- `python3 -m compileall -q backend/app backend/alembic backend/tests`: Passed.
- `PYTHONPATH=. pytest -q` from `backend/`: **23 passed, 3 skipped** (PostgreSQL live integration tests skipped when `TEST_DATABASE_URL` is unset).
- `alembic history`: Verified linear revision chain through `0003_r42_universal_scheduling`.
- `bash -n scripts/test-postgres-rls-compose.sh scripts/test-postgres-rls.sh`: Valid shell syntax.
- JSON and Pydantic schema validation for `branch_schedule.json` and `appointment.json`: Passed.
