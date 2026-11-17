# Build Verification Record — R4.2.2 & R4.3.0

Version: 4.3.0 (Cross-Branch Blind Upsert, Omnichannel Gemini/WhatsApp Integration & Full English Documentation).

## Verified Checks

- `python3 -m compileall -q backend/app backend/alembic backend/tests`: Passed (60 Python files compiled cleanly).
- `PYTHONPATH=. python3 tests/test_customer_scope_r422.py`: **11 passed, 0 failed** (branch-scoped customer visibility, 15s refresh token grace window, and RLS preservation in migration `0005`).
- `PYTHONPATH=. python3 tests/test_dst_policy_r421.py`: **7 passed, 0 failed**.
- `PYTHONPATH=. python3 tests/test_omnichannel_r430.py`: **6 passed, 0 failed** (Chilean/international phone normalization, sanitized cross-branch payload, Gemini branch-isolated conversation turns, and Twilio HMAC-SHA1 signature verification).
- `SHA256SUMS.txt`: Regenerated and verified across all repository files.
