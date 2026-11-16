# Changelog

## 4.3.0 — Resolución de clientes entre sucursales (Blind Upsert) y Canales Voz/WhatsApp con Gemini

### Añadido

- **Estándar de industria para agendamiento entre sucursales (`Blind Upsert` + `POST /customers/resolve-phone`):** Permite a cualquier sucursal agendar por teléfono o WhatsApp a un cliente que ya existe en otra sucursal de la misma empresa indicando su teléfono exacto, sin depender del administrador y sin exponer el historial ni datos de otras sucursales.
- `POST /appointments` ahora acepta `customer_phone` + `customer_name` directamente en la creación de la cita.
- **Agente conversacional por sucursal (`app/integrations/gemini/agent.py`):** Orquestador acotado al `branch_id` y `tenant_id` (bajo RLS) y endpoint `POST /channels/omnichannel/turn`.
- **Adaptador de Webhooks WhatsApp y Voz (`app/integrations/twilio/webhooks.py`):** Normalización de remitentes `whatsapp:+569...` y validación criptográfica `X-Twilio-Signature` (HMAC-SHA1).
- Suite de pruebas unitarias `backend/tests/test_omnichannel_r430.py` (6 pruebas nuevas).


## 4.2.2 — Acceso a clientes por sucursal y sesiones entre pestañas

### Añadido

- Clientes con sucursal de origen (`home_branch_id`), migración `0005_r422_customer_home_branch`. Relleno inicial con la sucursal de la primera reserva.
- `POST /customers` acepta `branch_id` opcional. Usuarios con una sola sucursal no lo necesitan.
- Regla de visibilidad documentada en `docs/security/CUSTOMER_SCOPE.md`, con pruebas sin base de datos.

### Corregido

- `GET /customers` solo devuelve clientes visibles para el usuario. Antes lo veía toda la empresa.
- `POST /appointments` no acepta clientes no visibles para el usuario. Responde 404 sin confirmar que existan.
- Un teléfono duplicado responde 409 con mensaje genérico, sin datos del cliente existente.
- Renovación de sesión: un refresh token revocado hace menos de 15 s se rechaza como renovación concurrente y no cierra todas las sesiones. Pasado ese plazo sí se considera robo.
- Frontend: las pestañas duplicadas adoptan el token rotado (`BroadcastChannel`) y la renovación va en cola (`navigator.locks`). Se reintenta una vez antes de cerrar sesión.
- "Próximas reservas" pide solo reservas desde el momento actual.

### Pendiente

- Verificación de correo y respuesta genérica en registro (enumeración de correos, N5).
- Tokens fuera de `sessionStorage` con cookies `HttpOnly` (N8).
- Carrera residual en la renovación si dos pestañas renuevan antes de recibir el mensaje; el servidor la limita con la ventana de 15 s.
- Ejecutar pruebas con PostgreSQL y Docker: no ejecutadas en este entorno.

## 4.2.1 — Corrección de la auditoría R4.2

### Corregido

- CORS permite `PUT`; los endpoints de horarios ya pueden llamarse desde el navegador.
- Límites de intentos en `/auth/register`, `/auth/login` y `/auth/refresh` por IP, y en login por correo. Usa Redis con respaldo en memoria. Configurable con `RATE_LIMIT_ENABLED`; `TRUST_PROXY_HEADERS` solo detrás de un proxy de confianza.
- Horas locales ambiguas (atraso de reloj) y horas inexistentes (adelanto) no se ofrecen ni se reservan. Política en `docs/scheduling/DST_POLICY.md`.
- La consulta de reservas no depende de la medianoche local, que puede no existir por DST.
- Reuso de un refresh token ya rotado cierra todas las sesiones activas del usuario y queda auditado.
- `audit_logs` es de solo inserción para el rol de runtime (migración `0004_r421_audit_append_only`).
- `backend/.dockerignore` evita copiar `.env` y cachés a la imagen.
- Frontend: versión visible actualizada y precios en formato CLP.

### Pendiente

- Verificación de correo y respuesta genérica en registro (enumeración de correos).
- Filtro de clientes por sucursal, decisión de producto.
- Tokens del frontend fuera de `sessionStorage`.
- Pruebas completas con PostgreSQL y Docker: no ejecutadas en este entorno.

## 4.2.0 — Motor universal de agenda

### Añadido

- Horarios semanales y pausas para sucursales, profesionales y recursos, con aislamiento RLS y FKs compuestas.
- Validación de zonas horarias IANA y configuración local de sucursal; reservas en UTC.
- Endpoints de recursos y consulta/reemplazo de horarios/pausas.
- Dependencias de tipos React (`@types/react`, `@types/react-dom`) y versión de frontend alineada a R4.2.
- Endpoint de disponibilidad por fecha, servicio y profesional/recurso, considerando duración y buffer.
- Validación de horarios y pausas al crear reservas.
- Cancelación auditada de reservas pendientes/confirmadas.
- Exclusión temporal PostgreSQL para evitar doble reserva de profesionales y recursos, incluso con solicitudes concurrentes externas a la API.
- Pruebas unitarias de horarios/DST y pruebas de integración concurrente con PostgreSQL real.

### Corregido / endurecido

- La prevención de solapamientos ya no depende únicamente de advisory locks de la API: PostgreSQL aplica la garantía final con `btree_gist` y `EXCLUDE`.
- Las reservas canceladas liberan el intervalo sin borrar el historial.

### Migración

- Alembic `0003_r42_universal_scheduling` agrega tablas horarias protegidas con RLS, campos de cancelación y restricciones de exclusión.
- La migración falla explícitamente si detecta zonas horarias inválidas, servicios fuera de rango, estados desconocidos o solapamientos activos preexistentes.
- En instalaciones con volumen PostgreSQL anterior a R4.2, un administrador debe instalar `btree_gist` una vez; el rol migrator no recibe `CREATE` sobre la base.

### Pendiente / fuera de alcance

- Ejecutar Docker Compose, migración y pruebas reales RLS/concurrencia en el Mac del usuario.
- Build React/Vite pendiente: no se instalaron dependencias en este entorno; se añadieron `@types/react` y `@types/react-dom` al manifiesto.
- Feriados, excepciones por fecha, turnos nocturnos/cruce de medianoche, reprogramación y políticas de cancelación por anticipación.
- Twilio, Gemini, WhatsApp, notificaciones y billing.

## 4.1.0 — Seguridad y núcleo SaaS

### Añadido

- Refresh tokens con JTI hasheado, almacenamiento por sesión, rotación de un solo uso y logout.
- Índice global mínimo `auth_identities` para resolver tenant en login sin bypass de RLS sobre `users`.
- Gestión API de usuarios y asignación explícita a sucursales.
- Roles `SUPER_ADMIN`, `TENANT_ADMIN`, `BRANCH_MANAGER`, `OPERATOR` y `READ_ONLY` con control de permisos en endpoints.
- Auditoría consultable por administradores.
- RLS `ENABLE` + `FORCE` en la tabla raíz `tenants`, tablas de negocio, sesiones y asignaciones.
- Claves foráneas compuestas para impedir relaciones cruzadas entre tenants.

### Corregido

- El contexto de tenant se reaplica al iniciar cada transacción SQLAlchemy.
- Eliminado el bypass `app.auth_lookup` que permitía consultar globalmente `users` durante login.
- Bloqueos separados para profesional y recurso en reservas concurrentes.

### Pendiente / fuera de alcance

- Pruebas reales de PostgreSQL/Docker y build frontend según el entorno de desarrollo.
- Twilio, Gemini, WhatsApp, notificaciones y billing.
