# Build Verification Record — R4.2.1

Version: 4.2.1 (Security & DST Hardening Patch).

## Verified Checks

- `python3 -m compileall -q backend/app backend/alembic backend/tests`: Passed across all Python modules.
- `PYTHONPATH=. python3 tests/test_dst_policy_r421.py`: **7 passed, 0 failed** (validates ambiguous fall-back hours, nonexistent spring-forward hours in `America/Santiago`, fixed-window rate limiter, Redis memory fallback, and append-only audit log migration).
