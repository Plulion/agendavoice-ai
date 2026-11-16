# AgendaVoice AI — R4.2.2

Versión 4.2.2: añade acceso a clientes por sucursal y corrige sesiones entre pestañas. Antes, 4.2.1 corrigió los hallazgos de la auditoría de R4.2 (ver `docs/audit/`). No certificada para producción hasta ejecutar pruebas con PostgreSQL y Docker.

**R4.2 — Motor universal de agenda** amplía el núcleo SaaS multiempresa/multisucursal de R4.1 con horarios semanales, pausas, disponibilidad, cancelación y protección de reservas concurrentes a nivel PostgreSQL. El primer vertical comercial sigue siendo salones y barberías. Este paquete no declara el MVP completo ni integra telefonía/IA real.

## Qué incluye R4.2

- Conserva autenticación, refresh rotativo, roles, permisos por sucursal, RLS `ENABLE` + `FORCE` y claves foráneas compuestas tenant-safe de R4.1.
- Horarios semanales de sucursal, profesionales y recursos, expresados en hora local de la sucursal.
- Pausas semanales para sucursales, profesionales y recursos.
- Zona horaria IANA validada por sucursal; reservas persistidas como instantes `timestamptz` en UTC.
- Disponibilidad por fecha, servicio, profesional y/o recurso, calculada con duración y buffer.
- Creación de reservas que valida horario completo, pausas, futuro, sucursal y asignaciones.
- Cancelación auditada; las reservas canceladas dejan de bloquear intervalos.
- Advisory locks en la API y restricciones PostgreSQL `EXCLUDE USING gist` para impedir solapamientos incluso entre procesos o clientes distintos.
- Pruebas unitarias de reglas horarias, pausas, validación de semana y cambio DST; pruebas de integración concurrente para profesional y recurso.

## Estado de verificación de este paquete

| Comprobación | Resultado |
|---|---|
| Compilación sintáctica Python | Ejecutada en construcción |
| Pruebas unitarias | Ejecutadas en construcción; resultado indicado en la entrega |
| Integración PostgreSQL/RLS/concurrencia | Incluida; requiere `TEST_DATABASE_URL` migrada y rol runtime sin `SUPERUSER`/`BYPASSRLS` |
| Docker Compose | No ejecutado en el entorno de construcción |
| Build React/Vite | Intentado; bloqueado porque no hay `node_modules` instalados. Se añadieron los tipos React faltantes al manifiesto. |
| Twilio/Gemini | No implementados; fuera del alcance |

No se declara verificada la exclusión concurrente en PostgreSQL hasta ejecutar la suite de integración contra una base real. Las pruebas unitarias no sustituyen esa comprobación.

## Inicio local en macOS

```bash
cp .env.example .env
# Edita JWT_SECRET y las contraseñas locales.
docker compose up --build
```

- Panel: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

La API ejecuta `alembic upgrade head` antes de iniciar. En bases nuevas, `infra/postgres/init.sql` instala `btree_gist` como superusuario durante el bootstrap.

La migración R4.2 valida zonas horarias, duración/buffer, estados, asignaciones a sucursal y reservas activas preexistentes. Si detecta solapamientos, se detiene y entrega los IDs que deben corregirse antes de reintentar.

La extensión `btree_gist` se instala como superusuario en el bootstrap inicial. En volúmenes PostgreSQL R4.1 ya existentes, ejecutar una vez antes de migrar:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

No se concede `CREATE` sobre la base al rol `agendavoice_migrator`.

## Configurar horarios

Cada sucursal debe tener una configuración semanal completa (lunes=0 a domingo=6). Para un día cerrado, enviar `is_closed: true` sin horas; para un día abierto, `opens_at` y `closes_at` en formato `HH:MM:SS`. Las pausas deben quedar dentro del horario del día.

- `GET/PUT /branches/{branch_id}/schedule`: horario y pausas de sucursal.
- `GET/PUT /staff/{staff_id}/schedule`: horario específico del profesional; si nunca se configura, hereda el horario de sucursal.
- `GET/PUT /resources/{resource_id}/schedule`: horario específico del recurso; si nunca se configura, hereda el horario de sucursal.
- `GET /availability?day=YYYY-MM-DD&branch_id=...&service_id=...&staff_id=...&resource_id=...`: devuelve inicios disponibles en UTC y hora local. Debe indicarse al menos profesional o recurso.
- `POST /appointments`: crea la reserva si el intervalo completo cabe en horarios y no colisiona.
- `POST /appointments/{id}/cancel`: cancela una reserva pendiente/confirmada y libera el intervalo.

La configuración semanal usa hora local IANA de la sucursal; las reservas se guardan en UTC. Los servicios que cruzan medianoche no se aceptan en esta fase: deben modelarse como ventanas separadas.

## Pruebas

Suite unitaria:

```bash
cd backend
python -m pip install -r requirements.txt
pytest -q
```

Pruebas reales de RLS y concurrencia PostgreSQL, en una base local aislada:

```bash
./scripts/test-postgres-rls-compose.sh
```

El script aplica migraciones y ejecuta `test_postgres_rls.py` y `test_postgres_scheduling_concurrency.py` con el rol runtime `agendavoice_app`. No apuntar a producción.

## Límites conocidos

- El refresh token sigue en `sessionStorage`; antes de producción debe migrarse a cookie HttpOnly/Secure/SameSite con protección CSRF.
- No hay reglas de feriados/excepciones por fecha, turnos que crucen medianoche ni calendarios externos.
- Los profesionales y recursos heredan el horario de sucursal hasta que se configure su horario específico.
- No hay edición completa de reservas, reprogramación ni reglas de cancelación por anticipación.
- No hay Twilio, Gemini, WhatsApp, notificaciones, worker ni billing.
- El panel React no incorpora aún un calendario visual; los nuevos flujos se exponen por API/Swagger.

## Documentación

- `CHANGELOG.md`, `VERSION`
- `docs/architecture/OVERVIEW.md`
- `docs/security/R4.1_SECURITY.md`
- `docs/scheduling/R4.2_SCHEDULING.md`
- `docs/BUILD_VERIFICATION_R4.2.md`
- `docs/BUILD_VERIFICATION_R4.2.1.md`
- `docs/audit/AUDITORIA_R4.2_Y_CORRECCION_4.2.1.md`
- `docs/scheduling/DST_POLICY.md`
- `docs/security/CUSTOMER_SCOPE.md`
- `docs/BUILD_VERIFICATION_R4.2.2.md`
- `docs/api/ENDPOINTS.md`
- `docs/deployment/LOCAL_MACOS.md`
- `docs/uml/ERD.mmd`
