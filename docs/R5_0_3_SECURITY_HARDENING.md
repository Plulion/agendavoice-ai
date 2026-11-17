# AgendaVoice AI R5.0.3 — Security Hardening & Audit Remediation Report

## Scope

Built directly on top of `agendavoice-ai-R5.0.2-local.zip` to close all remaining high- and medium-severity security and workflow findings identified during the R5.0.2 cross-audit.

## Remediated Findings (R5.0.2 -> R5.0.3)

| ID | Finding | Resolution in R5.0.3 |
| :--- | :--- | :--- |
| **A1** | `POST /customers/resolve-phone` exposed `id` and `name` for customers belonging exclusively to another branch | `sanitize_cross_branch_customer()` now returns a privacy-preserving notice without `id`, `name`, `email`, or `home_branch_id`. |
| **A2** | `POST /appointments` allowed `data.customer_email` to redirect confirmation emails (with another customer's name) to an arbitrary address | `resolve_confirmation_recipient()` enforces that existing customers ALWAYS receive confirmations at their stored DB email. For cross-branch bookings, `customer.name` is omitted from the email body/HTML. |
| **A4** | `POST /appointments` had no rate limit on booking creation or email sending | Added fixed-window rate limits per operator (`30/hour`) and per recipient email address (`5/hour`) on both creation and resend endpoints. |
| **M3** | Confirmation emails displayed raw UTC timestamps instead of branch local time | Added `format_appointment_local_time()` converting timestamps into `ZoneInfo(branch.timezone)` (e.g., `18/11/2026 15:00 (America/Santiago, UTC-03:00)`). |
| **M4** | No resend workflow for failed or expired pending confirmation emails | Added `POST /appointments/{appointment_id}/resend-confirmation` (branch-scoped, rate-limited, rotates token, expires previous tokens, logs `appointment.confirmation_resent`). |
| **M6** | SMTP client lacked TLS and authentication support for production relays | Added optional `SMTP_USE_TLS`, `SMTP_USERNAME`, and `SMTP_PASSWORD` in `config.py`, `.env.example`, and `email.py` (`STARTTLS` + `SMTP.login`), defaulting to `SMTP_USE_TLS=false` for local Mailpit. |
| **N1** | Confirmation token format only checked length (`32..200`) and interpolated directly in JS string | Enforced strict regex `^[A-Za-z0-9_-]{32,200}$` on both GET and POST, added GET preview rate limit, and serialized the token with `json.dumps(token)`. |
| **N2** | Omnichannel turn requested email but did not extract emails from follow-up messages | Added `extract_email_from_text()` in `agent.py` and automatic email recognition in `parse_natural_intent()` and `omnichannel_turn()`. |
| **N3** | Brand-new omnichannel customers defaulted to literal name `"Cliente"` | Made `OmnichannelTurnIn.sender_name` optional; for new customers missing a real name, returns `NAME_REQUIRED` and asks for full name before creating a customer record. |
| **N4** | Omnichannel existing-customer lookup checked only normalized phone, missing legacy raw formats | Updated `_book_fn()` to query both normalized and raw phone strings (`or_`), matching `_resolve_or_create_customer_by_phone()`. |
| **B4** | `POST /ai/local/chat` exposed raw `str(exc)` network details in HTTP 503 | Exception is logged server-side; API returns a generic 503 message. |
| **N7 & Hygiene** | Frontend version drift (`5.0.0` vs `5.0.2`), Spanish report inside English `docs/` | Aligned `VERSION`, FastAPI, `frontend/package.json`, `frontend/src/App.tsx`, and `docs/index.html` to `5.0.3`; replaced Spanish report with this English report; verified zero `.pyc` files in archive. |

## Verification Status

- Python compilation (`py_compile` across all backend `.py` files): **PASS**.
- Zero-dependency unit tests (`test_customer_scope_r422.py`, `test_dst_policy_r421.py`, `test_omnichannel_r430.py`, `test_r503_security_fixes.py`): **PASS** (verified in sandbox).
- Shell syntax (`bash -n` on all `.sh` scripts): **PASS**.
- `SHA256SUMS.txt` cryptographic integrity: **PASS** (100% file match, zero `.pyc` files).
- **Pending local Mac execution:** `docker compose up --build`, full `pytest -q` (with `pydantic[email]`), `./scripts/test-postgres-rls-compose.sh`, Mailpit delivery verification, and `cd frontend && npm install && npm run build`.
