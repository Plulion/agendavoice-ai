from datetime import datetime
import pytest
from app.schemas import RegisterIn, BranchIn, ServiceIn, AppointmentIn

def test_registration_password_minimum():
    with pytest.raises(Exception):
        RegisterIn(company_name="Salón Demo", admin_name="Admin", email="admin@example.com", password="short")

def test_branch_timezone_default():
    assert BranchIn(name="Sucursal Centro").timezone == "America/Santiago"

def test_service_duration_must_be_positive():
    with pytest.raises(Exception):
        ServiceIn(name="Corte", duration_minutes=0, price=10000)

def test_appointment_requires_timezone():
    with pytest.raises(Exception):
        AppointmentIn(branch_id=1, customer_id=1, service_id=1, staff_id=1,
                      starts_at=datetime(2027,1,1,10,0))
