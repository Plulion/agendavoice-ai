from pathlib import Path
from app.schemas import CustomerProfileUpdateIn, OmnichannelTurnIn, WaitlistIn


def test_omnichannel_turn_accepts_optional_customer_email():
    payload = OmnichannelTurnIn(
        branch_id=1, sender_phone="+56912345678", message="Quiero reservar",
        service_id=1,
    )
    assert payload.customer_email is None
    payload_with_email = OmnichannelTurnIn(
        branch_id=1, sender_phone="+56912345678", message="Quiero reservar",
        service_id=1, customer_email="cliente@example.com",
    )
    assert str(payload_with_email.customer_email) == "cliente@example.com"


def test_customer_profile_update_preserves_omitted_fields():
    payload = CustomerProfileUpdateIn(email=None)
    assert payload.model_fields_set == {"email"}
    assert payload.first_name is None
    assert payload.last_name is None


def test_waitlist_model_input_contains_customer_id_only_once():
    payload = WaitlistIn(
        branch_id=1, customer_id=2, service_id=3,
        preferred_from="2027-01-01T10:00:00-03:00",
        preferred_to="2027-01-01T11:00:00-03:00",
    )
    values = payload.model_dump()
    assert list(values).count("customer_id") == 1
    assert values["customer_id"] == 2


def test_r5_migration_uses_fully_qualified_composite_fk_targets():
    migration = Path(__file__).parents[1] / "alembic/versions/0006_r5_customer_confirmation_history.py"
    source = migration.read_text()
    assert '["branches.tenant_id", "branches.id"]' in source
    assert '["customers.tenant_id", "customers.id"]' in source
    assert '["services.tenant_id", "services.id"]' in source
    assert '["staff.tenant_id", "staff.branch_id", "staff.id"]' in source


def test_omnichannel_booking_requests_email_before_booking():
    from app.integrations.gemini.agent import run_branch_conversation_turn
    result = run_branch_conversation_turn(
        company_name="Salón Demo", branch_name="Centro", branch_timezone="America/Santiago",
        sender_phone="+56912345678", sender_name="Cliente", message="Quiero agendar",
        check_availability_fn=lambda: [],
        book_appointment_fn=lambda: {"status": "EMAIL_REQUIRED"},
    )
    assert result["appointment"] is None
    assert "correo electrónico" in result["reply"]


def test_omnichannel_booking_says_pending_email_confirmation():
    from app.integrations.gemini.agent import run_branch_conversation_turn
    result = run_branch_conversation_turn(
        company_name="Salón Demo", branch_name="Centro", branch_timezone="America/Santiago",
        sender_phone="+56912345678", sender_name="Cliente", message="Quiero agendar",
        check_availability_fn=lambda: [],
        book_appointment_fn=lambda: {"id": 7, "starts_at": "2027-01-01T10:00:00+00:00", "status": "PENDING"},
    )
    assert "pendiente" in result["reply"]
    assert "confirmes" in result["reply"]
