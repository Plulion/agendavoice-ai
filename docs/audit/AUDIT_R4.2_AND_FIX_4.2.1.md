# Security & Concurrency Audit Log (R4.2 -> R4.3.0)

This document records the static and dynamic audit findings across releases R4.2, R4.2.1, R4.2.2, and R4.3.0.

## Summary of Audited Findings & Remediations

| ID | Finding | Severity | Resolution Status |
| :--- | :--- | :--- | :--- |
| **H1** | CORS blocked `PUT` requests required by schedule endpoints | High | **Fixed (R4.2.1):** Added `PUT` to `allow_methods` in `CORSMiddleware`. |
| **H2** | Missing rate limiting on `/auth/register`, `/auth/login`, and `/auth/refresh` | High | **Fixed (R4.2.1):** Implemented `FixedWindowLimiter` backed by Redis with automatic in-memory fallback. |
| **H4** | Ambiguous local DST hours accepted silently during fall-back transitions | Medium | **Fixed (R4.2.1):** `local_slot_to_utc` rejects both nonexistent and ambiguous local wall-clock times (`docs/scheduling/DST_POLICY.md`). |
| **N1** | Runtime DB role (`agendavoice_app`) had `UPDATE`/`DELETE` privileges on `audit_logs` | High | **Fixed (R4.2.1):** Migration `0004_r421_audit_append_only` revokes `UPDATE` and `DELETE` on `audit_logs`. |
| **N2** | Reusing a rotated refresh token did not revoke active sessions on suspected theft | High | **Fixed (R4.2.1 & R4.2.2):** Reuse outside the 15-second concurrent tab grace window revokes all active user sessions and logs `auth.refresh_reuse_detected`. |
| **N4** | Missing `.dockerignore` allowed `.env` and caches into Docker build context | Medium | **Fixed (R4.2.1):** Added `backend/.dockerignore`. |
| **N6** | `GET /customers` exposed customers across all branches of a company | Medium | **Fixed (R4.2.2):** Added `home_branch_id` (migration `0005`) and `_customer_scope` filtering by origin branch or visit history. |
| **N13** | Multi-tab concurrent token refresh caused false-positive session termination | Medium | **Fixed (R4.2.2):** Added Web Locks (`navigator.locks`), `BroadcastChannel` token adoption, and a 15s server grace window. |
| **R4.3-1** | Branch B operators received `409 Conflict` when booking an existing Branch A customer by phone | High (Ops) | **Fixed (R4.3.0):** Added industry-standard **Blind Upsert** (`POST /customers/resolve-phone` and inline `customer_phone` in `POST /appointments`) with rate limiting and sanitized cross-branch payloads. |
| **R4.3-2** | Voice (Gemini) and WhatsApp (Twilio) integration modules were empty placeholders | Medium | **Fixed (R4.3.0):** Implemented branch-scoped Gemini 2.5 Flash orchestrator (`agent.py`), Twilio HMAC-SHA1 validator (`webhooks.py`), and `POST /channels/omnichannel/turn`. |
