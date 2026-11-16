# AgendaVoice AI — Arquitectura R4.2

## Principios

AgendaVoice AI es un SaaS universal multiempresa y multisucursal. El núcleo compartido concentra identidad, tenant, sucursales, usuarios/permisos, clientes, catálogo, agenda, notificaciones, suscripciones y auditoría. Las reglas particulares se implementan en módulos verticales. El primer vertical comercial previsto es salones/barberías.

R4.2 incorpora el hito **Motor universal de agenda** sobre la fundación de seguridad R4.1. No debe confundirse con el MVP integrado.

## Capas

- **API:** FastAPI, autenticación JWT, autorización por rol y sucursal.
- **Dominio:** módulos identity, tenants, branches, customers, catalog, scheduling, subscriptions, audit. Scheduling contiene horarios semanales y pausas para sucursales, profesionales y recursos.
- **Persistencia:** SQLAlchemy 2, PostgreSQL y Alembic. Las reservas se persisten en UTC; los horarios recurrentes usan hora local IANA de la sucursal.
- **Aislamiento:** contexto transaccional `app.tenant_id` + RLS `ENABLE/FORCE`, incluida la tabla raíz `tenants`.
- **Sesiones:** access JWT corto y refresh JWT rotativo, persistido mediante hash de JTI.
- **Frontend:** React, TypeScript y Vite; tokens en sessionStorage en esta versión.
- **Concurrencia de agenda:** advisory locks en API y `EXCLUDE USING gist` con `btree_gist` en PostgreSQL para profesionales y recursos.
- **Servicios auxiliares:** Redis disponible en Compose; Twilio/Gemini continúan como integración pendiente.

## Flujo de autenticación

1. Registro crea tenant, usuario administrador, identidad global mínima, suscripción y sesión de refresh.
2. Login busca `auth_identities` por correo normalizado; obtiene solo `user_id` y `tenant_id`.
3. El backend fija `app.tenant_id` y consulta `users` bajo RLS para verificar contraseña y estado.
4. El access token contiene `sub`, `tenant_id`, rol informativo, `iat`, `exp` y tipo. La autorización usa el rol consultado desde DB, no el claim del cliente.
5. Refresh valida sesión, bloquea la fila, revoca el token anterior y emite un nuevo par en la misma transacción.

## Flujo de contexto tenant

`Session.info['tenant_id']` conserva el tenant autenticado durante el request. El evento `after_begin` establece el GUC con `set_config(..., true)` al inicio de cada transacción. Esto evita que el `COMMIT` de una operación quite el contexto necesario para una consulta ORM posterior y evita dejar un GUC persistente en una conexión del pool.

## Permisos

`TENANT_ADMIN` administra el tenant. `BRANCH_MANAGER`, `OPERATOR` y `READ_ONLY` tienen asignaciones explícitas en `user_branch_access`. El acceso se comprueba tanto en la API como en RLS a nivel tenant. R4.1 no implementa administración global cross-tenant.

## Estado de roadmap

- **R4.0:** fundación modular multiempresa/multisucursal.
- **R4.1:** seguridad y núcleo SaaS.
- **R4.2:** motor universal de agenda (horarios, pausas, disponibilidad, cancelación y exclusión concurrente en PostgreSQL).

## Próximos hitos

- **R4.3:** vertical salones/barberías.
- **R4.4:** Twilio, orquestador conversacional y Gemini.
- **R4.5:** panel administrativo completo.
- **R4.6:** validación integrada y piloto.
