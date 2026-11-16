# R4.2.1 — Registro de verificación de construcción

Versión: 4.2.1 (parche correctivo de R4.2). Ver hallazgos en `docs/audit/AUDITORIA_R4.2_Y_CORRECCION_4.2.1.md`.

## Ejecutado en el entorno de corrección

- `python3 -m compileall -q backend/app backend/alembic backend/tests`: correcto, 50 archivos Python.
- `py_compile` de `app/main.py`, `app/core/config.py`, `app/core/rate_limiter.py`, `app/modules/scheduling/availability.py`: correcto.
- `PYTHONPATH=. python3 tests/test_dst_policy_r421.py` desde `backend/`: **7 aprobadas, 0 fallidas**.
  Cubre horas ambiguas y inexistentes de Santiago 2026, conversión única, límite de intentos, reinicio de ventana,
  respaldo en memoria si Redis falla, independencia de claves y regla de auditoría append-only.
- Aserciones de la prueba existente `test_local_slot_conversion_handles_dst_gap` reproducidas con la lógica nueva.
- Comparación de 4.2.0 contra 4.2.1 para todo 2026 en pasos de 15 min: solo cambian 4 franjas, el 4-abr-2026 de 23:00 a 23:45.
- Verificación de `SHA256SUMS.txt` del paquete de entrada: todas las entradas coinciden.

## Omitido: no ejecutado en el entorno de corrección

- `pytest` completo. El entorno no tiene FastAPI, SQLAlchemy, pydantic, redis ni pytest, y no tiene red para instalarlos.
- Migraciones con `alembic upgrade head` (incluida 0004) sobre PostgreSQL real.
- Pruebas de integración RLS y concurrencia (`TEST_DATABASE_URL`).
- `docker compose up` y `scripts/test-postgres-rls-compose.sh`.
- Peticiones HTTP reales: preflight CORS con `PUT`, respuestas 429, flujo de reuso de refresh token.
- `npm install && npm run build`.

## Próximo paso obligatorio

```bash
docker compose up -d db redis
cd backend && PYTHONPATH=. pytest -q
TEST_DATABASE_URL=postgresql+psycopg://postgres:...@localhost:5432/agendavoice_test pytest -q tests/integration
cd ../frontend && npm install && npm run build
```

Hasta completar esos pasos, esta versión no debe presentarse como certificada ni usarse con datos reales.
