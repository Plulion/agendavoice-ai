# REST API Reference (v4.3.0)

Local base URL: `http://localhost:8000`. Interactive OpenAPI / Swagger UI: `/docs`.

## 1. Core SaaS, Identity & Branch Management

| Method | Route | Minimum Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | Database and Redis connectivity health check |
| `POST` | `/auth/register` | Public | Registers a new company (`tenant`), admin user, and returns `access_token` + `refresh_token` |
| `POST` | `/auth/login` | Public | Authenticates user by email; verifies password hash under tenant RLS |
| `POST` | `/auth/refresh` | Refresh Token | Rotates single-use refresh token (with 15s grace window for concurrent tabs) |
| `POST` | `/auth/logout` | Refresh Token | Revokes the presented refresh session |
| `GET` | `/me` | Authenticated | Returns current user profile, `tenant_id`, role, and authorized `branch_ids` |
| `GET/POST` | `/users` | Admin | Lists and creates branch-scoped users (`BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`) |
| `GET/POST` | `/branches` | Read / Admin | Lists visible branches for the user; creates new branches |
| `GET/POST` | `/services` | Read / Admin | Lists and creates catalog services (`duration_minutes`, `buffer_minutes`, `price`) |
| `GET/POST` | `/staff` | Read / Manager | Lists and creates branch professionals |
| `GET/POST` | `/customers` | Read / Operator | Lists branch-visible customers and registers new customers |
| `POST` | `/customers/resolve-phone` | Operator | **R4.3.0:** Rate-limited exact phone lookup/upsert (`+569...`) for cross-branch phone booking |
| `GET` | `/audit-logs` | Admin | Lists recent append-only audit events (`limit` 1–500) |

---

## 2. Universal Scheduling & Omnichannel AI Engine

| Method | Route | Minimum Role | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/resources` | Manager / Admin | Creates a bookable physical resource in an authorized branch |
| `GET` | `/resources` | Authenticated | Lists visible physical resources (supports optional `branch_id` filter) |
| `GET/PUT` | `/branches/{branch_id}/schedule` | Manager / Admin | Retrieves or replaces the 7-day opening hours and breaks for a branch |
| `GET/PUT` | `/staff/{staff_id}/schedule` | Manager / Admin | Retrieves or replaces custom 7-day hours and breaks for a professional |
| `GET/PUT` | `/resources/{resource_id}/schedule` | Manager / Admin | Retrieves or replaces custom 7-day hours and breaks for a resource |
| `GET` | `/availability` | Authenticated | Computes available UTC and local slots for `day`, `branch_id`, `service_id`, and `staff_id`/`resource_id` |
| `POST` | `/appointments` | Operator | Creates an appointment (supports `customer_id` or inline `customer_phone` Blind Upsert) |
| `POST` | `/appointments/{id}/cancel` | Operator | Cancels a pending/confirmed appointment and releases the time slot |
| `POST` | `/channels/omnichannel/turn` | Operator | **R4.3.0:** Executes a branch-isolated Gemini 2.5 Flash Voice or WhatsApp booking turn |
