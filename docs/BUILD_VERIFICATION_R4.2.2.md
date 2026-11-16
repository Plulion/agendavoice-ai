# R4.2.2 — Registro de verificación de construcción

Versión 4.2.2. Cambios: acceso a clientes por sucursal (migración 0005), ventana de reuso de refresh token, sincronización de sesiones entre pestañas y "próximas reservas".

## Ejecutado en el entorno de corrección

- `python3 -m compileall -q backend/app backend/alembic backend/tests`: correcto.
- `py_compile` de `main.py`, `schemas.py`, `customers/models.py` y la migración 0005: correcto.
- `PYTHONPATH=. python3 tests/test_customer_scope_r422.py`: **11 aprobadas, 0 fallidas.** Cubre la regla de visibilidad, la ventana de reuso y que la migración respete RLS.
- `PYTHONPATH=. python3 tests/test_dst_policy_r421.py`: **7 aprobadas, 0 fallidas** (regresión de 4.2.1).
- Verificación de `SHA256SUMS.txt` del paquete entregado.

## No ejecutado (sin Docker, PostgreSQL, FastAPI, SQLAlchemy ni red)

- `pytest` completo, incluidas las 23 pruebas originales.
- `alembic upgrade head` sobre PostgreSQL, incluidas las migraciones 0004 y 0005 y el relleno de `home_branch_id`.
- Pruebas HTTP de visibilidad: un encargado de la sucursal A no ve clientes exclusivos de B, y no puede reservar para ellos.
- Concurrencia de renovación de sesión en navegador real.
- `npm install && npm run build`: el TypeScript de `api.ts` no se compiló aquí.

## Próximo paso obligatorio

```bash
docker compose up -d db redis
cd backend && PYTHONPATH=. pytest -q
TEST_DATABASE_URL=... pytest -q tests/integration
cd ../frontend && npm install && npm run build
```

Antes de presentarlo como libre de errores, esos comandos deben pasar.
