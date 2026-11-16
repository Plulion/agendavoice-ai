# Modelo de amenazas — AgendaVoice AI R4.1

## Activos

Datos de clientes, credenciales, reservas, profesionales, sucursales, configuración del tenant, sesiones de usuario y registros de auditoría.

## Amenazas principales y controles

| Amenaza | Control R4.1 | Riesgo/pendiente |
|---|---|---|
| Usuario cambia `tenant_id` en petición | El tenant se deriva del JWT verificado; no se acepta en payloads | Validar con suite PostgreSQL y pruebas API |
| Consulta ORM olvida filtro tenant | RLS `ENABLE` + `FORCE` y políticas `USING/WITH CHECK` | Ejecutar prueba real con rol runtime |
| Contexto queda pegado en conexión del pool | `set_config(..., true)` + `Session.info` + `after_begin` | Validar en PostgreSQL con pool real |
| Login requiere saltarse RLS | `auth_identities` mínimo; `users` nunca tiene bypass | Revisar tasa de login y enumeración |
| Reutilización de refresh token | JTI hash persistido, `FOR UPDATE`, revocación y rotación | Agregar detección/alerta de reuse y revocación global |
| Usuario accede a otra sucursal | Tabla `user_branch_access` y validación de rutas | Completar pruebas API por rol |
| Elevación de privilegios | Roles permitidos en esquema, endpoint de creación limitado | No existe flujo de invitaciones/edición |
| Contraseña expuesta | bcrypt vía Passlib | Añadir política de bloqueo y rate limiting |
| Token robado desde navegador | Refresh token en `sessionStorage` | Migrar a cookie HttpOnly/Secure/SameSite antes de producción |
| Auditoría manipulada | Eventos de auditoría por operaciones relevantes | Evaluar append-only y retención centralizada |

## Límites de confianza

- `agendavoice_app` no debe ser superusuario, propietario de tablas ni tener `BYPASSRLS`.
- `agendavoice_migrator` solo se usa para migraciones.
- `app.tenant_id` es un GUC de contexto confiado desde la aplicación; RLS mitiga omisiones de filtro, pero una inyección SQL arbitraria con credenciales runtime podría cambiarlo. RLS no reemplaza la prevención de SQL injection.
- `auth_identities` es un índice global de autenticación sin password hash. La tabla `tenants` también está protegida por RLS; el alta reserva el ID de secuencia antes de insertar.
- Los secretos de `.env` no deben versionarse.

## Validaciones requeridas antes de producción

1. Prueba de RLS ejecutada con PostgreSQL real y rol runtime.
2. Pruebas API negativas para cada rol y tenant.
3. Revisión de cookies/CSRF y estrategia de refresh.
4. Rate limiting de login/refresh y protección anti-enumeración.
5. Revisión independiente de migraciones, permisos SQL y procedimientos de backup.
