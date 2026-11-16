# API R4.2

Base local: `http://localhost:8000`. Documentación interactiva: `/docs`.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/health` | Público | Estado de DB/Redis |
| POST | `/auth/register` | Público | Crea tenant y administrador; devuelve access + refresh |
| POST | `/auth/login` | Público | Login por correo; consulta de usuario bajo RLS |
| POST | `/auth/refresh` | Refresh token | Rotación de sesión; el token anterior queda revocado |
| POST | `/auth/logout` | Refresh token | Revoca la sesión presentada |
| GET | `/me` | Autenticado | Perfil, tenant y sucursales permitidas |
| GET/POST | `/users` | Admin | Lista y crea usuarios de sucursal (`BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`) |
| GET/POST | `/branches` | Lectura / Admin | Consulta sucursales visibles y crea sucursales |
| GET/POST | `/services` | Lectura / Admin | Consulta y crea servicios |
| GET/POST | `/staff` | Lectura / Admin o manager asignado | Consulta y crea profesionales |
| GET/POST | `/customers` | Lectura / Admin, manager u operador | Consulta y crea clientes |
| GET | `/audit-logs` | Admin | Últimos eventos de auditoría (`limit` 1–500) |
| GET/POST | `/appointments` | Lectura / Admin, manager u operador asignado | Consulta y crea reservas |

Las rutas mutables rechazan `READ_ONLY`. El tenant nunca se acepta desde el body: se deriva del JWT verificado. Las rutas con `branch_id` comprueban la asignación del usuario además de la pertenencia al tenant.

Los endpoints de agenda siguen siendo la implementación inicial de R4.0; no representan todavía disponibilidad basada en horarios laborales, pausas ni cancelación.

## API R4.2 — Agenda universal

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| POST | `/resources` | Admin / manager asignado | Crea recurso físico en una sucursal |
| GET | `/resources` | Autenticado | Lista recursos visibles; admite `branch_id` |
| GET/PUT | `/branches/{branch_id}/schedule` | Admin / manager asignado | Reemplaza 7 días de horario y pausas de sucursal |
| GET/PUT | `/staff/{staff_id}/schedule` | Admin / manager asignado | Define horario y pausas particulares del profesional |
| GET/PUT | `/resources/{resource_id}/schedule` | Admin / manager asignado | Define horario y pausas particulares del recurso |
| GET | `/availability` | Autenticado | Calcula slots libres por `day`, `branch_id`, `service_id` y al menos uno de `staff_id`/`resource_id`; `slot_minutes` opcional (5–60) |
| POST | `/appointments` | Admin / manager / operador asignado | Crea reserva si cabe en horarios, pausas y no se solapa |
| POST | `/appointments/{appointment_id}/cancel` | Admin / manager / operador asignado | Cancela reserva pendiente/confirmada; acepta `reason` opcional |

Los horarios se envían como hora local `HH:MM:SS`; `weekday` usa lunes=0 a domingo=6. `ScheduleConfigIn` requiere exactamente los siete días. Un día cerrado usa `is_closed: true` y no lleva apertura/cierre. Las pausas deben estar dentro de la ventana de apertura.

El horario de profesional/recurso hereda el de sucursal mientras no exista configuración propia. Una vez configurado, restringe la ventana de la sucursal. La duración ocupada de una reserva es duración del servicio más buffer. `starts_at` debe incluir offset ISO-8601 y se normaliza a UTC.

Las reservas activas (`PENDING`, `CONFIRMED`) no pueden solaparse para un mismo profesional ni para un mismo recurso. PostgreSQL aplica restricciones `EXCLUDE` además de los advisory locks de la API. Los errores de concurrencia se devuelven como HTTP 409.

## Cambios 4.2.1

- Los endpoints `/auth/register`, `/auth/login` y `/auth/refresh` pueden responder `429` con cabecera `Retry-After`.
- `PUT` está permitido por CORS para `/branches/{id}/schedule`, `/staff/{id}/schedule` y `/resources/{id}/schedule`.
- `GET /availability` omite horas ambiguas o inexistentes por DST.

## Cambios 4.2.2

- `GET /customers` solo devuelve clientes visibles para el usuario.
- `POST /customers` acepta `branch_id` opcional. Con varias sucursales y sin `branch_id`, responde 422.
- `POST /appointments` responde 404 si el cliente no es visible para el usuario.
- `GET /appointments` sin `from_at` sigue devolviendo todo. El panel pide `from_at` = ahora.
