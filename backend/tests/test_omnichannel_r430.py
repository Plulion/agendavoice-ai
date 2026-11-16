"""Pruebas unitarias de R4.3.0:
- Resolución segura de clientes entre sucursales por teléfono exacto (Blind Upsert)
- Agente conversacional Gemini acotado por sucursal
- Verificación criptográfica de webhooks de WhatsApp / Voz (Twilio HMAC-SHA1)
"""
from pathlib import Path
from app.modules.customers.visibility import (
    customer_visible,
    normalize_phone,
    sanitize_cross_branch_customer,
)
from app.integrations.gemini.agent import (
    build_branch_system_prompt,
    run_branch_conversation_turn,
)
from app.integrations.twilio.webhooks import (
    extract_channel_and_phone,
    verify_twilio_signature,
)


def test_phone_normalization_chile_and_international():
    assert normalize_phone("9 1234 5678") == "+56912345678"
    assert normalize_phone("56912345678") == "+56912345678"
    assert normalize_phone("+56 9 8765 4321") == "+56987654321"


def test_cross_branch_sanitized_payload_hides_other_branch_metadata():
    payload = sanitize_cross_branch_customer(15, "  Carolina Pérez ", "912345678")
    assert payload == {
        "id": 15,
        "name": "Carolina Pérez",
        "phone": "+56912345678",
        "cross_branch_linked": True,
    }
    assert "home_branch_id" not in payload
    assert "email" not in payload


def test_customer_becomes_visible_to_branch_b_after_blind_upsert_booking():
    # Antes de agendar en Sucursal 2 (cliente registrado en Sucursal 1): no visible en listados de Sucursal 2
    assert customer_visible([2], home_branch_id=1, visited_branch_ids=[1]) is False
    # Después de agendar por teléfono exacto en Sucursal 2: pasa a ser visible en Sucursal 2
    assert customer_visible([2], home_branch_id=1, visited_branch_ids=[1, 2]) is True


def test_gemini_branch_agent_availability_and_booking_turns():
    prompt = build_branch_system_prompt("Webfinanzas Corp", "Sucursal Las Condes", "America/Santiago")
    assert "Sucursal Las Condes" in prompt
    assert "No tienes acceso" in prompt

    avail_turn = run_branch_conversation_turn(
        company_name="Webfinanzas Corp",
        branch_name="Sucursal Las Condes",
        branch_timezone="America/Santiago",
        sender_phone="912345678",
        sender_name="Pedro",
        message="Hola, ¿tienen horas disponibles para mañana?",
        check_availability_fn=lambda: [{"local_starts_at": "2026-11-17T10:30:00-03:00"}],
    )
    assert avail_turn["intent"] == "availability"
    assert "10:30" in avail_turn["reply"]

    book_turn = run_branch_conversation_turn(
        company_name="Webfinanzas Corp",
        branch_name="Sucursal Las Condes",
        branch_timezone="America/Santiago",
        sender_phone="912345678",
        sender_name="Pedro",
        message="Quiero confirmar la hora de las 10:30",
        check_availability_fn=lambda: [],
        book_appointment_fn=lambda: {"id": 99, "starts_at": "2026-11-17T10:30:00-03:00", "status": "CONFIRMED"},
    )
    assert book_turn["intent"] == "book"
    assert book_turn["appointment"]["id"] == 99
    assert "#99" in book_turn["reply"]


def test_whatsapp_and_voice_webhook_extraction_and_signature():
    channel, phone = extract_channel_and_phone("whatsapp:+56911223344")
    assert channel == "WHATSAPP"
    assert phone == "+56911223344"

    v_channel, v_phone = extract_channel_and_phone("+56999887766")
    assert v_channel == "VOICE"
    assert v_phone == "+56999887766"

    # Verifica firma HMAC-SHA1
    url = "https://api.webfinanzas.cl/webhooks/whatsapp"
    params = {"From": "whatsapp:+56911223344", "Body": "Hola"}
    token = "super_secret_twilio_token"
    import base64, hashlib, hmac
    raw = url + "BodyHolaFromwhatsapp:+56911223344"
    sig = base64.b64encode(hmac.new(token.encode(), raw.encode(), hashlib.sha1).digest()).decode()
    assert verify_twilio_signature(url, params, sig, token) is True
    assert verify_twilio_signature(url, params, "bad_sig", token) is False


def test_main_exposes_resolve_phone_and_omnichannel_routes():
    text = (Path(__file__).parents[1] / "app" / "main.py").read_text()
    assert '"/customers/resolve-phone"' in text
    assert '"/channels/omnichannel/turn"' in text
    assert "_resolve_or_create_customer_by_phone" in text


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
