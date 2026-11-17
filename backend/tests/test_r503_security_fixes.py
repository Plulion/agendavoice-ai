"""Regression & security hardening unit tests for R5.0.3 (stdlib-only, pytest-compatible).

Verifies:
- A1: Cross-branch resolve-phone leaks neither customer id nor customer name.
- A2: Existing customers always receive confirmation emails strictly at stored email (no hijack).
- A4: Rate limiting enforced on POST /appointments (per user & per recipient email) and resend endpoint.
- M3: Confirmation emails format appointment timestamps in the branch's local IANA timezone.
- M4: POST /appointments/{appointment_id}/resend-confirmation endpoint present & rate-limited.
- M6: SMTP adapter supports optional STARTTLS and SMTP authentication.
- N1: Strict regex validation for confirmation tokens and json.dumps() serialization in JS.
- N2/N3/N4: Omnichannel free-text email extraction, NAME_REQUIRED prompt, and dual phone lookup.
- B4: Local Ollama HTTP 503 hides raw internal exception details.
- Version consistency across VERSION, FastAPI, frontend/package.json, App.tsx, and docs/index.html.
"""
from datetime import datetime, timezone
from pathlib import Path
from app.modules.customers.visibility import sanitize_cross_branch_customer
from app.modules.notifications.formatting import (
    format_appointment_local_time,
    is_valid_confirmation_token_format,
    resolve_confirmation_recipient,
)
from app.integrations.gemini.agent import (
    extract_email_from_text,
    parse_natural_intent,
    run_branch_conversation_turn,
)

BACKEND_ROOT = Path(__file__).parents[1]
REPO_ROOT = BACKEND_ROOT.parent
MAIN_PY = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
EMAIL_PY = (BACKEND_ROOT / "app" / "modules" / "notifications" / "email.py").read_text(encoding="utf-8")
SCHEMAS_PY = (BACKEND_ROOT / "app" / "schemas.py").read_text(encoding="utf-8")


def test_a1_cross_branch_resolve_hides_id_and_name():
    result = sanitize_cross_branch_customer("9 8765 4321")
    assert result["cross_branch_linked"] is True
    assert result["requires_admin_review"] is True
    assert result["phone"] == "+56987654321"
    for secret_field in ("id", "name", "email", "home_branch_id", "rut"):
        assert secret_field not in result
    assert "sanitize_cross_branch_customer(phone=customer.phone)" in MAIN_PY


def test_a2_existing_customer_cannot_redirect_confirmation_email():
    # Existing customer with stored email ignores caller-supplied attacker email
    assert resolve_confirmation_recipient(
        created_new_customer=False,
        stored_email="real.client@example.com",
        requested_email="attacker@evil.com",
    ) == "real.client@example.com"
    # Existing customer without stored email cannot be sent to caller-supplied email
    assert resolve_confirmation_recipient(
        created_new_customer=False,
        stored_email=None,
        requested_email="attacker@evil.com",
    ) is None
    # New customer uses the email provided on creation
    assert resolve_confirmation_recipient(
        created_new_customer=True,
        stored_email=None,
        requested_email="new.client@example.com",
    ) == "new.client@example.com"
    assert "include_customer_name=not was_other_branch" in MAIN_PY


def test_a4_appointments_and_resend_enforce_rate_limits():
    assert 'enforce_rate_limit(f"appointment-create:' in MAIN_PY
    assert 'enforce_rate_limit(f"appointment-email:' in MAIN_PY
    assert 'enforce_rate_limit(f"appointment-resend:' in MAIN_PY


def test_m3_confirmation_email_formats_branch_local_time():
    # Nov 18, 2026 18:00 UTC = 15:00 in America/Santiago (UTC-03:00 summer time)
    utc_dt = datetime(2026, 11, 18, 18, 0, tzinfo=timezone.utc)
    formatted = format_appointment_local_time(utc_dt, "America/Santiago")
    assert "18/11/2026 15:00" in formatted
    assert "America/Santiago" in formatted
    assert "UTC-03:00" in formatted
    # Winter time (May 10, 2026 14:00 UTC = 10:00 America/Santiago UTC-04:00)
    winter_dt = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)
    winter_fmt = format_appointment_local_time(winter_dt, "America/Santiago")
    assert "10/05/2026 10:00" in winter_fmt
    assert "UTC-04:00" in winter_fmt


def test_m4_resend_confirmation_endpoint_exists():
    assert '@app.post("/appointments/{appointment_id}/resend-confirmation")' in MAIN_PY
    assert '"appointment.confirmation_resent"' in MAIN_PY


def test_m6_smtp_supports_starttls_and_auth():
    assert "smtp.starttls(" in EMAIL_PY
    assert "smtp.login(" in EMAIL_PY
    assert "settings.smtp_use_tls" in EMAIL_PY
    assert "settings.smtp_username" in EMAIL_PY


def test_n1_confirmation_token_regex_and_safe_json_embedding():
    valid_token = "AbCdEf0123456789_-AbCdEf0123456789_-"
    assert is_valid_confirmation_token_format(valid_token) is True
    assert is_valid_confirmation_token_format("short") is False
    assert is_valid_confirmation_token_format(valid_token + "';alert(1);//") is False
    assert is_valid_confirmation_token_format(valid_token + "<script>") is False
    assert "json.dumps(token)" in MAIN_PY
    assert "pattern=r\"^[A-Za-z0-9_-]{32,200}$\"" in SCHEMAS_PY


def test_n2_n3_omnichannel_extracts_email_and_requests_real_name():
    assert extract_email_from_text("Mi correo es Maria.Perez@Example.CL gracias") == "maria.perez@example.cl"
    assert extract_email_from_text("Hola buenas tardes") is None
    assert parse_natural_intent("mi correo es ana@example.com")["intent"] == "book"

    name_prompt = run_branch_conversation_turn(
        company_name="Salón Demo",
        branch_name="Providencia",
        branch_timezone="America/Santiago",
        sender_phone="+56912345678",
        sender_name=None,
        message="Quiero reservar una hora",
        check_availability_fn=lambda: [],
        book_appointment_fn=lambda: {"status": "NAME_REQUIRED"},
    )
    assert name_prompt["appointment"] is None
    assert "nombre y apellido" in name_prompt["reply"]


def test_n4_omnichannel_dual_phone_lookup():
    assert "or_(Customer.phone == normalized_phone, Customer.phone == data.sender_phone.strip())" in MAIN_PY


def test_b4_ollama_error_does_not_leak_exception_string():
    assert "raise HTTPException(503, str(exc))" not in MAIN_PY
    assert "logger.warning(" in MAIN_PY


def test_version_alignment_across_project():
    if (REPO_ROOT / "VERSION").exists():
        assert (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "5.0.3"
        assert '"version":"5.0.3"' in (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        assert "R5.0.3" in (REPO_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        assert "5.0.3" in (REPO_ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'version="5.0.3"' in MAIN_PY
    assert '"version": "5.0.3"' in MAIN_PY


if __name__ == "__main__":
    import sys
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as exc:
                failures += 1
                print("FAIL", name, exc)
    sys.exit(1 if failures else 0)
