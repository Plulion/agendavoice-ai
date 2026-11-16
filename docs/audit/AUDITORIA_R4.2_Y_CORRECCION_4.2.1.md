# Auditoría de AgendaVoice AI R4.2 y corrección 4.2.1

**Paquete auditado:** `AgendaVoice-AI-R4_2.zip`, SHA-256 `8201e6f6…868ccd0`, 149 entradas, 97.954 bytes.
**Fuente:** auditoría previa realizada con ChatGPT, más revisión directa del código.
**Resultado:** R4.2 sigue sin certificarse para producción. Esta versión 4.2.1 corrige los defectos verificados
por análisis estático. Nada de esto ha sido ejecutado contra PostgreSQL ni Docker (ver `BUILD_VERIFICATION_R4.2.1.md`).

## 1. Verificación de las afirmaciones del documento de ChatGPT

| Afirmación | Resultado | Evidencia |
|---|---|---|
| SHA-256 y 149 entradas | Confirmada | `sha256sum` y `unzip -l` |
| Los 50 archivos Python compilan | Confirmada | `compileall` sobre `backend/app`, `alembic`, `tests` |
| 23 pruebas aprobadas, 3 omitidas | **No verificable en el entorno de auditoría** | Faltan FastAPI, SQLAlchemy, pydantic, pytest y red. Hay 26 funciones `test_`, coherente con 23+3 |
| Migraciones con `ENABLE` + `FORCE` RLS | Confirmada en el código | Migraciones 0001, 0002 y 0003 |
| Protección de solapamientos con `EXCLUDE ... gist` | Confirmada en el código | Migración 0003. No ejecutada contra PostgreSQL |
| Frontend incompleto (módulos con solo README) | Confirmada | `frontend/src/modules/*` contiene únicamente `README.md` |
| Ambigüedad DST sin política explícita | Confirmada y **medida** | Con `fold=0`, 4 franjas de 15 min del 4-abr-2026 se aceptaban sin aviso |

## 2. Hallazgos del documento de ChatGPT

| ID | Hallazgo | Prioridad | Estado en 4.2.1 |
|---|---|---|---|
| H1 | CORS no permite `PUT`; los 3 endpoints de horarios fallan desde el navegador | Alta | **Corregido.** `PUT` agregado en `allow_methods` |
| H2 | Sin límite de intentos en registro, login y refresh | Alta | **Corregido en parte.** Límites por IP y por correo con Redis y respaldo en memoria. Pendiente: verificación de correo y medidas anti-automatización |
| H3 | Frontend no es un panel operativo; falta calendario | Media | **Pendiente.** Es trabajo de desarrollo, no de corrección |
| H4 | Horas ambiguas DST sin política | Media | **Corregido.** Ambiguas y inexistentes se rechazan. Ver `docs/scheduling/DST_POLICY.md` |
| H5 | Funciones pendientes (reprogramación, feriados, notificaciones, worker, Twilio, Gemini) | Media | **Pendiente.** Son alcance futuro, no defectos |

## 3. Hallazgos nuevos (no estaban en el documento de ChatGPT)

| ID | Hallazgo | Prioridad | Estado en 4.2.1 |
|---|---|---|---|
| N1 | El rol de runtime podía `UPDATE` y `DELETE` sobre `audit_logs` por los privilegios por defecto de `init.sql`. Un fallo podía borrar el rastro de auditoría | Alta | **Corregido.** Migración `0004_r421_audit_append_only` |
| N2 | Reusar un refresh token ya rotado devolvía 401, pero no cerraba las sesiones del usuario ante posible robo | Alta | **Corregido.** Reuso fuera de 15 s revoca todas las sesiones activas del usuario y queda auditado. Dentro de esa ventana se trata como renovación concurrente |
| N3 | La consulta de reservas usaba la medianoche local como inicio de día. En Santiago la medianoche puede no existir | Baja | **Corregido** como robustez. Ventana UTC amplia y solapamiento exacto por intervalo |
| N4 | Sin `.dockerignore`: `COPY . .` llevaba `.env`, `__pycache__` y `.pytest_cache` a la imagen | Media | **Corregido.** `backend/.dockerignore` |
| N5 | El registro responde 409 "El correo ya está registrado", lo que permite enumerar correos. El login no lo hace | Media | **Pendiente.** Atenuado por el límite de registro. Decisión de producto: respuesta genérica con verificación de correo |
| N6 | `GET /customers` no filtra por sucursal. Un `BRANCH_MANAGER`, `OPERATOR` o `READ_ONLY` ve teléfonos y correos de todas las sucursales | Media | **Corregido en 4.2.2.** Cliente de empresa con acceso restringido por sucursal de origen y reservas (migración 0005) |
| N7 | `auth_identities` es legible por el rol de runtime sin RLS: índice global de correos. Es intencional para el login, pero una inyección SQL expondría todos los correos | Media | **Riesgo aceptado y documentado.** Mitigado por consultas parametrizadas |
| N8 | El frontend guarda access y refresh tokens en `sessionStorage`, accesibles desde JavaScript (riesgo ante XSS) | Media | **Pendiente.** Evaluar cookies `HttpOnly` con `SameSite` en la fase de producción |
| N9 | El frontend mostraba "R4.1" como versión y precios con `$` sin formato CLP | Baja | **Corregido** |
| N10 | "Próximas reservas" lista todas las reservas sin filtro de fecha | Baja | **Corregido en 4.2.2.** Consulta solo reservas desde la fecha actual |
| N11 | Con `TRUST_PROXY_HEADERS=true` se confía en `X-Forwarded-For`. Un proxy mal configurado permite evadir el límite | Media | **Mitigado.** Desactivado por defecto; documentado |
| N12 | Límite por correo (10 intentos cada 15 min) permite bloquear temporalmente una cuenta a un tercero | Baja | **Riesgo aceptado** y documentado |
| N13 | Dos pestañas que renuevan a la vez con el mismo refresh token ahora cierran la sesión | Media | **Corregido en 4.2.2.** Web Locks, adopción del token rotado por `BroadcastChannel` y ventana de 15 s en el servidor. Queda una carrera residual documentada en `CUSTOMER_SCOPE.md` y en el changelog |

## 4. Orden recomendado para la siguiente versión

1. Ejecutar pruebas reales: `scripts/test-postgres-rls-compose.sh`, `pytest` completo y migraciones 0001 a 0004 sobre PostgreSQL 16.
2. Probar CORS con `PUT` desde el navegador y los límites 429 contra Redis.
3. Probar el flujo de reuso de refresh token con dos clientes.
4. `npm install && npm run build` en `frontend/`.
5. Decidir N5 y N8 antes de cualquier piloto.
6. Implementar el calendario visual (H3) y la integración con Twilio y Gemini (H5).

## 5. Qué no garantiza esta corrección

Es un análisis estático más correcciones aplicadas por lectura de código. No certifica RLS, concurrencia real,
el arranque con Docker ni el build de React. Esas pruebas siguen pendientes y deben ejecutarse en un entorno con Docker y PostgreSQL.
