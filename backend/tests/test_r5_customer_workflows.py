from datetime import datetime, timezone, timedelta
import pytest
from app.modules.customers.rut import is_valid_chilean_rut, normalize_rut
from app.schemas import CustomerIn, WaitlistIn, CustomerProfileUpdateIn

def test_chilean_rut_valid_and_invalid():
    assert is_valid_chilean_rut("12.345.678-5")
    assert is_valid_chilean_rut("11.111.111-1")
    assert not is_valid_chilean_rut("12.345.678-9")
    assert normalize_rut("12.345.678-k") == "12345678K"

def test_customer_can_be_created_from_first_and_last_name():
    customer = CustomerIn(first_name="María", last_name="González", phone="+56912345678", email="maria@example.com")
    assert customer.first_name == "María"
    assert customer.last_name == "González"

def test_customer_requires_name_or_first_and_last():
    with pytest.raises(ValueError):
        CustomerIn(phone="+56912345678")

def test_waitlist_requires_aware_ordered_range():
    start = datetime.now(timezone.utc) + timedelta(days=1)
    item = WaitlistIn(branch_id=1, customer_id=2, service_id=3, preferred_from=start, preferred_to=start+timedelta(days=2))
    assert item.preferred_to > item.preferred_from
    with pytest.raises(ValueError):
        WaitlistIn(branch_id=1, customer_id=2, service_id=3, preferred_from=start, preferred_to=start-timedelta(days=1))

def test_customer_profile_fields_are_validated():
    profile = CustomerProfileUpdateIn(first_name="Ana", last_name="Pérez", rut="12.345.678-5", email="ana@example.com")
    assert profile.email == "ana@example.com"


def test_ollama_adapter_parses_local_response(monkeypatch):
    import json
    from app.integrations.llm.ollama import OllamaChatProvider
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"message": {"content": "Hola, ¿qué servicio buscas?"}}).encode()
    monkeypatch.setattr("app.integrations.llm.ollama.urlopen", lambda *args, **kwargs: FakeResponse())
    answer = OllamaChatProvider().chat([{"role": "user", "content": "Hola"}])
    assert answer == "Hola, ¿qué servicio buscas?"
