# Modelo de datos

- `tenants`: empresas.
- `users`: usuarios, roles y pertenencia a empresa.
- `auth_identities`: índice global mínimo email/usuario/tenant para localizar identidad antes del login (sin hash de contraseña).
- `refresh_sessions`: JTI hasheado, expiración y revocación de refresh tokens.
- `user_branch_access`: asignaciones de usuarios operativos a sucursales.
- `branches`: sucursales, dirección, teléfono y zona horaria.
- `customers`: clientes por empresa.
- `services`: catálogo, duración, buffer, precio y moneda.
- `staff`: profesionales por sucursal y especialidades.
- `resources`: sillones/salas/recursos físicos por sucursal.
- `appointments`: reservas con fechas UTC y estado.
- `subscriptions`: plan/estado inicial.
- `audit_logs`: eventos administrativos.

Los atributos propios de vehículos, salas de spa o bahías de taller deben residir en sus verticales, no en la tabla universal de recursos.


En R4.1, las tablas tenant-scoped usan RLS con `ENABLE` y `FORCE`; `tenants` filtra por `id` y el contexto transaccional `app.tenant_id`. `auth_identities` es la excepción global limitada del flujo de autenticación.

R4.2 agrega:

- `branch_hours` / `branch_breaks`: ventana semanal y pausas de cada sucursal.
- `staff_hours` / `staff_breaks`: horario y pausas particulares por profesional; si no hay horario propio, hereda el de sucursal.
- `resource_hours` / `resource_breaks`: horario y pausas particulares por recurso; si no hay horario propio, hereda el de sucursal.
- `appointments.cancelled_at` y `appointments.cancellation_reason`: trazabilidad de cancelación sin borrar la reserva.

Las seis tablas horarias tienen RLS `ENABLE` + `FORCE`, políticas por `app.tenant_id` y FKs compuestas tenant/sucursal/entidad. Los horarios son hora local semanal; los instantes de reservas son UTC.

Las referencias a profesional/recurso desde una reserva y desde sus horarios usan una FK compuesta `(tenant_id, branch_id, entity_id)`. Así PostgreSQL impide asignar un profesional o recurso de otra sucursal de la misma empresa, además de impedir referencias entre tenants.
