# Desarrollo local en macOS — R4.2

## Requisitos

- Docker Desktop con Docker Compose v2.
- Git y navegador moderno.
- Puertos locales disponibles: 5432 (PostgreSQL), 6379 (Redis), 8000 (API), 5173 (Vite).

## Arranque

```bash
cp .env.example .env
# Cambia JWT_SECRET y las contraseñas locales antes de compartir el entorno.
docker compose up --build
```

La API ejecuta `alembic upgrade head` antes de iniciar Uvicorn. En una base existente R4.0/R4.1 se aplican las migraciones pendientes hasta R4.2; si se trata de una base desechable local y el esquema quedó en un estado incompatible, respalda primero y recrea el volumen solo si aceptas perder esos datos.

- Panel: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Pruebas

Suite unitaria:

```bash
cd backend
python -m pip install -r requirements.txt
pytest -q
```

Prueba RLS real en una base aislada local, con Docker Compose:

```bash
cd ..
./scripts/test-postgres-rls-compose.sh
```

El script crea `agendavoice_test`, concede conexión a los roles locales, aplica migraciones y ejecuta la prueba con `agendavoice_app` (sin `SUPERUSER`, `BYPASSRLS` ni propiedad de tablas). La prueba crea y elimina tenants temporales. No la ejecutes contra producción.

## Variables importantes

- `JWT_SECRET`: mínimo 32 caracteres; usar un valor aleatorio distinto por entorno.
- `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`: duración de sesiones.
- `CORS_ORIGINS`: orígenes explícitos, separados por coma.
- `TEST_DATABASE_URL`: solo para pruebas de integración.

La extensión `btree_gist` se instala como superusuario en el bootstrap. En volúmenes existentes, ejecuta `CREATE EXTENSION IF NOT EXISTS btree_gist;` conectado a `agendavoice` antes de migrar. El rol `agendavoice_migrator` no recibe `CREATE` sobre la base. No configures credenciales reales de Twilio/Gemini: esas integraciones siguen fuera del alcance R4.2.
