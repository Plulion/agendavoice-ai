# AgendaVoice AI — Master Functional Specification R5

## Product definition

AgendaVoice AI is a universal multi-tenant SaaS platform for appointment-based businesses. The first vertical is salons/barber shops. A shared core owns tenant identity, branches, users, customers, scheduling, communications, audit and permissions. Vertical modules define service-specific workflows and terminology.

## Product principles

1. Local-first development: Docker Compose, PostgreSQL, Redis, Mailpit and optional Ollama. Paid providers remain disabled until local acceptance tests pass.
2. The LLM never writes directly to the database. It may request approved application tools; the backend validates tenant, role, branch, state and business rules.
3. Every tenant-owned table must have tenant isolation. Branch users additionally see only authorized branches and customer history allowed by the customer visibility policy.
4. A requested appointment is not confirmed until the customer explicitly confirms the email link.
5. Appointment history is a snapshot of completed work, not a list of all reservations.
6. Customer staff preferences are separate from the professional actually assigned to an appointment.
7. Customer consent is versioned and auditable. Marketing consent is separate from operational messages.

## Core modules

### CORE
- Tenants, subscription metadata, users, RBAC and branch access.
- Branches, time zones, business hours, breaks and exceptions.
- Customers, contact methods, consent records and privacy-aware visibility.
- Scheduling engine, resources, availability, appointment lifecycle and audit.
- Email outbox and notification adapters.

### SALON (first vertical)
- Services, durations, buffers, prices and service categories.
- Professionals, specialties and customer preferences per branch/service.
- Salon resources: chairs, wash basins, manicure tables and treatment rooms.
- Customer visit history, product catalogue and promotion enquiries.

### SPA (future vertical)
- Therapists, cabins, treatment packages, equipment and preparation rules.

### AUTOMOTIVE (future vertical)
- Vehicles, mechanics, workshop bays, service jobs, parts and estimated job duration.

## Customer journey

1. Ask whether the caller is new or returning.
2. Returning customer: resolve by normalized phone within the tenant; request an additional verification step before disclosing personal history.
3. New customer: capture first name, last name, phone and email; collect RUT only where required by the business process; validate it; record applicable consent.
4. Identify requested service and branch.
5. Ask whether the customer prefers a particular professional; retrieve branch/service-specific preference when available.
6. Check professional skills, schedules, branch hours, breaks, resources and appointment conflicts.
7. Offer alternatives. Never silently substitute a preferred professional.
8. Create a PENDING appointment and send a unique, expiring email confirmation link.
9. Confirm only when the link is used. Release expired unconfirmed reservations.
10. On completion, create a service-history snapshot with service, professional, date/time and branch.
11. Offer a post-visit satisfaction survey or next-visit reminder only under the business's communication rules and consent.

## Appointment lifecycle

`PENDING -> CONFIRMED -> COMPLETED`

Alternative terminal states: `CANCELLED`, `NO_SHOW`. Expired `PENDING` reservations are cancelled/released. A future rescheduling workflow must be atomic: validate the replacement slot first, then move the appointment in one transaction while preserving the audit trail.

## Email confirmation

- Confirmation token: cryptographically random, one-time, stored as SHA-256 hash.
- Expiry: tenant-configurable; current R5 setting defaults to 30 minutes.
- Email outbox: delivery status, attempts, timestamp and error.
- Local test SMTP: Mailpit; no external email service required.
- A failed send must not silently become a confirmed appointment. The reservation remains pending and the failure is visible in the outbox.
- Do not persist the raw confirmation token in the outbox.

## Customer records and privacy

- Tenant-scoped uniqueness for phone and optional RUT.
- First name and last name are distinct fields; legacy display name remains for compatibility.
- Operational notifications and marketing communications require separate policy handling.
- Customer history must be filtered by tenant and branch visibility and must not be disclosed based on name/phone alone.
- Data retention, correction, export and deletion workflows must be specified against applicable Chilean privacy law before production release.

## Commercial modules (later releases)

- Product catalogue, variants, branch stock and promotion enquiry in a later MVP increment.
- Checkout, payments, receipts, returns and full inventory accounting after the core booking flow is stable.
- Gift cards, memberships, loyalty, campaigns and reactivation after consent/opt-out handling is implemented.

## Admin and analytics

- Owner, tenant administrator, branch manager, operator and read-only roles.
- Admin can create/edit/cancel bookings, block calendars and manage staff/resources without the AI.
- Dashboard KPIs: bookings, occupancy, completions, cancellations, no-shows, new/repeat customers, service revenue and bookings created by AI.
- Conversational analytics must be grounded in tenant-scoped SQL aggregates, never LLM-generated guesses.

## Roadmap

### R5.0 foundation (this package)
Customer profile fields/RUT validation, consent records, professional preference records, email confirmation token and outbox, completed service history, basic waitlist records, local Ollama provider adapter, RLS migration and documentation.

### R5.1 salon workflow completion
New/returning customer conversation; customer verification; preference-aware staff selection; automatic rescheduling/cancellation; waitlist matching and notification; reminder scheduler; no-show workflow; multi-service appointments; full admin screens.

### R5.2 commercial layer
Products/variants/branch stock, promotions, basic sales records, post-visit surveys and loyalty rules.

### R6 integrations and scale
Telephony, WhatsApp/SMS, external email provider, payment integrations, cloud deployment, observability, backups/restore drills and additional verticals.

## Acceptance criteria for local MVP

- A tenant cannot read or mutate another tenant's customers, appointments, preferences, history or email records.
- A branch operator cannot read another branch's customer history unless the visibility policy permits it.
- RUT checksum and tenant uniqueness are enforced.
- Appointment conflicts are prevented under concurrent requests.
- Pending email-confirmation bookings occupy the slot only until confirmed or expired.
- An expired token cannot confirm an appointment.
- Completed appointment creates exactly one service-history record.
- The local email is inspectable in Mailpit.
- Ollama can answer a prompt without cloud credentials; no database records are included in its prompt.
- Unit and PostgreSQL integration tests pass before production consideration.
