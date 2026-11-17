# R5 API Additions (v5.0.3)

All routes except the public confirmation URL require an authenticated bearer token unless otherwise stated. Staff routes enforce tenant RLS and branch access control.

| Method | Route | Purpose |
| :--- | :--- | :--- |
| `POST` | `/customers` | Create customer; accepts `first_name`, `last_name`, normalized `phone`, optional `email`, optional validated `rut`; legacy `name` remains accepted |
| `POST` | `/customers/resolve-phone` | Rate-limited phone lookup/creation. Returns privacy-safe notice (no `id`/`name`) if customer belongs exclusively to another branch |
| `PUT` | `/customers/{customer_id}/profile` | Partial update of tenant-global names, RUT, and email (**restricted to `TENANT_ADMIN` / `SUPER_ADMIN`**) |
| `POST` | `/customers/{customer_id}/consents` | Append a versioned consent decision (`DATA_PROCESSING`, `EMAIL_MARKETING`) |
| `POST` | `/customers/{customer_id}/staff-preferences` | Store preferred professional by branch and optional service |
| `GET` | `/customers/{customer_id}/history` | Read completed service-history snapshots within staff visibility scope |
| `POST` | `/appointments` | Rate-limited creation of `PENDING` booking with local-timezone email confirmation sent strictly to stored email for existing customers |
| `POST` | `/appointments/{appointment_id}/resend-confirmation` | **R5.0.3:** Rate-limited token rotation and confirmation email resend for `PENDING` appointments |
| `GET` | `/public/appointments/confirm?token=...` | Rate-limited, strict-regex landing page (never mutates state) |
| `POST` | `/public/appointments/confirm` | Explicit, rate-limited, audited confirmation action (`PENDING -> CONFIRMED`) |
| `POST` | `/appointments/{appointment_id}/complete` | Mark confirmed appointment completed and create service-history snapshot |
| `POST` | `/waitlist` | Add customer to branch/service waitlist |
| `GET` | `/waitlist?branch_id=...` | List waiting entries for authorized branch |
| `POST` | `/channels/omnichannel/turn` | Branch-isolated Voice/WhatsApp turn with automatic email extraction and new-customer name prompt |
| `POST` | `/ai/local/chat` | Test configured local Ollama model; model has no business tools or database access |

Appointment statuses in R5: `PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`, `NO_SHOW`. Existing cancellation route remains `POST /appointments/{appointment_id}/cancel`.
