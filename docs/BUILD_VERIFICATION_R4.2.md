# R4.2 — Registro de verificación de construcción

Fecha de construcción: 2026-11-15.

## Ejecutado y aprobado

- `python -m compileall -q backend/app backend/alembic backend/tests` — correcto.
- `PYTHONPATH=. pytest -q` desde `backend/` — **23 passed, 3 skipped**.
- `alembic history` — cadena correcta; `0003_r42_universal_scheduling` aparece como `head`.
- `bash -n scripts/test-postgres-rls-compose.sh scripts/test-postgres-rls.sh` — correcto.
- Validación JSON de `frontend/package.json` y payloads de ejemplo — correcta.
- Validación Pydantic de los payloads `branch_schedule.json` y `appointment.json` — correcta.
- Import estructural de FastAPI y creación del metadata SQLAlchemy sobre SQLite, usando stubs para dependencias externas ausentes — correcto: 38 combinaciones método/ruta y 19 tablas. Esta comprobación no sustituye el arranque con dependencias reales ni una migración PostgreSQL.

## Omitido / no ejecutado

- Las 3 pruebas de integración PostgreSQL se omitieron porque `TEST_DATABASE_URL` no está configurada: aislamiento RLS, concurrencia por profesional y concurrencia por recurso.
- Docker Compose y PostgreSQL no se ejecutaron: Docker, `psql`, `pg_isready` y el driver `psycopg` no están disponibles en el entorno de construcción.
- La migración `0003_r42_universal_scheduling` no se aplicó a una base real. `alembic history` solo confirma la cadena de revisiones.
- `npm run build` se intentó, pero no pudo completarse porque no existe `frontend/node_modules` y React/react-dom no están instalados. El entorno no tiene conectividad para instalar dependencias. Se añadieron `@types/react` y `@types/react-dom` a `devDependencies` para corregir la carencia de declaraciones de tipos observada en la base R4.1.

## Consecuencia

R4.2 es un paquete de código y migración preparado, con pruebas unitarias aprobadas, pero **no se certifica todavía** el aislamiento RLS ni la exclusión concurrente sobre PostgreSQL real, ni el build del frontend. Antes de piloto deben ejecutarse `scripts/test-postgres-rls-compose.sh` en Docker Desktop y `npm install && npm run build`.
