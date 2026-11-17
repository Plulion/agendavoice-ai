# Local test plan

## Automated

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Manual acceptance sequence

1. Start Compose and verify API health, PostgreSQL, Redis and Mailpit.
2. Register a test tenant and create a branch, service and professional.
3. Create a customer with first name, last name, phone, email and a known valid test RUT. Confirm invalid RUT is rejected and duplicate tenant RUT returns conflict.
4. Record `DATA_PROCESSING` consent and separately record marketing consent.
5. Add a professional preference for that customer and branch; optionally scope it to a service.
6. Configure branch and staff schedules.
7. Create a booking with a customer email. Verify status is `PENDING` and an email appears in Mailpit.
8. Open the email confirmation link. Verify the browser displays a success page and the appointment becomes `CONFIRMED`.
9. Try the same link again; it should report that the appointment is already confirmed.
10. Complete the appointment through the staff API. Verify one service-history snapshot exists with service/professional/time.
11. Add and list a waitlist entry; verify branch authorization is enforced.
12. Use `/ai/local/chat` with Ollama installed. Verify it answers in Spanish and no customer details are sent.
13. Create a second tenant and attempt cross-tenant reads/writes. Expect denial under PostgreSQL RLS.
14. Run PostgreSQL RLS and scheduling concurrency integration tests using a disposable test DB.

## Expiry test

Set `APPOINTMENT_CONFIRMATION_MINUTES=2`, create a booking, wait for expiry, then request availability or create a new booking. The expired `PENDING` booking should be changed to `CANCELLED` and the slot released. A stale confirmation link must return HTTP 410.
