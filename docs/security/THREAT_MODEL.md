# Threat Model & Security Controls

## Protected Assets

Customer PII (names, phone numbers, emails), authentication credentials, branch schedules, staff assignments, appointments, refresh sessions, and append-only audit logs.

## Primary Threats & Implemented Mitigations

| Threat Vector | Implemented Control (R4.1 – R4.3.0) | Verification Method |
| :--- | :--- | :--- |
| **Cross-Tenant Data Leakage** | `tenant_id` derived strictly from verified JWT; PostgreSQL `ENABLE` + `FORCE RLS` and composite foreign keys on all tables. | `tests/integration/test_postgres_rls.py` |
| **Connection Pool Context Bleed** | Transaction-local `set_config('app.tenant_id', ..., true)` paired with `Session.after_begin` listener and `db.info.clear()` on teardown. | `test_tenant_context_listener_reapplies_after_commit` |
| **Cross-Branch Snooping (Intra-Tenant)** | `assert_branch_access()` on all branch routes + `_customer_scope()` filtering `GET /customers` by `home_branch_id` or branch visit history. | `tests/test_customer_scope_r422.py` |
| **Cross-Branch Customer Enumeration** | Rate-limited `POST /customers/resolve-phone` (15 req/min) returning sanitized `{id, name, phone}` payloads without leaking origin branch or prior visits. | `tests/test_omnichannel_r430.py` |
| **Refresh Token Replay / Theft** | Single-use hashed JTI rotation with 15s concurrent tab grace window and global session revocation on delayed reuse. | `tests/test_customer_scope_r422.py` |
| **Audit Trail Tampering** | Migration `0004` executes `REVOKE UPDATE, DELETE ON audit_logs FROM agendavoice_app`. | `tests/test_dst_policy_r421.py` |
| **Forged WhatsApp / Voice Webhooks** | Cryptographic HMAC-SHA1 validation (`verify_twilio_signature`) over `X-Twilio-Signature`. | `tests/test_omnichannel_r430.py` |
