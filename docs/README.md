# AgendaVoice AI (R5.0.3) — Technical Documentation Index

Welcome to the technical documentation for **AgendaVoice AI**, an enterprise multi-tenant and multi-branch scheduling engine built by **Webfinanzas Corp.**

---

## Interactive Architecture Showcase

* **[`index.html`](index.html)** — Interactive English technical showcase (GitHub Pages ready) featuring SVG architecture diagrams, RBAC matrices, API reference tables, and a live 4-scenario multi-branch simulator.

---

## Documentation Modules

### 1. Architecture & Data Model
* **[`architecture/OVERVIEW.md`](architecture/OVERVIEW.md)** — High-level layered architecture, authentication lifecycle, transaction context propagation, and roadmap.
* **[`architecture/COMPONENTS.mmd`](architecture/COMPONENTS.mmd)** — Mermaid component topology diagram.
* **[`MODEL_DATA.md`](MODEL_DATA.md)** — Relational schema overview, composite foreign keys, and tenant/branch isolation boundaries.
* **[`uml/ERD.mmd`](uml/ERD.mmd)** — Entity-Relationship Diagram (Mermaid).

### 2. Security, Multi-Tenancy & Branch Privacy
* **[`security/R4.1_SECURITY.md`](security/R4.1_SECURITY.md)** — PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY`, rotating refresh tokens, and role hierarchy.
* **[`security/CUSTOMER_SCOPE.md`](security/CUSTOMER_SCOPE.md)** — Branch-scoped customer visibility rules (`home_branch_id`, visit history, and Cross-Branch Blind Upsert).
* **[`security/THREAT_MODEL.md`](security/THREAT_MODEL.md)** — Assets, threat vectors, mitigations, and trust boundaries.

### 3. Universal Scheduling Engine & Timezone Policy
* **[`scheduling/R4.2_SCHEDULING.md`](scheduling/R4.2_SCHEDULING.md)** — Weekly schedules, breaks, inheritance rules, and PostgreSQL `EXCLUDE USING gist` concurrency protection.
* **[`scheduling/DST_POLICY.md`](scheduling/DST_POLICY.md)** — Daylight Saving Time (DST) handling for `America/Santiago` (ambiguous and nonexistent local hours).
* **[`scheduling/examples/`](scheduling/examples/)** — Sample JSON payloads for branch schedules, appointments, and availability queries.

### 4. API, Deployment & QA Verification
* **[`api/ENDPOINTS.md`](api/ENDPOINTS.md)** — Complete REST API reference for R5.0.3 (Auth, Branches, Schedules, Blind Upsert, Availability, Appointments, and Omnichannel turns).
* **[`deployment/LOCAL_MACOS.md`](deployment/LOCAL_MACOS.md)** — Local Docker Compose setup and live PostgreSQL RLS verification guide on macOS/Linux.
* **[`audit/AUDIT_R4.2_AND_FIX_4.2.1.md`](audit/AUDIT_R4.2_AND_FIX_4.2.1.md)** — Security and concurrency audit log and remediation matrix.
* **[`BUILD_VERIFICATION_R4.2.md`](BUILD_VERIFICATION_R4.2.md)** / **[`BUILD_VERIFICATION_R4.2.1.md`](BUILD_VERIFICATION_R4.2.1.md)** / **[`BUILD_VERIFICATION_R4.2.2.md`](BUILD_VERIFICATION_R4.2.2.md)** — Build and test verification records.

### 5. R5 Customer Workflows, Email Confirmation & Security Hardening
* **[`R5_MASTER_SPEC.md`](R5_MASTER_SPEC.md)** — Master R5 functional specification and roadmap.
* **[`R5_0_3_SECURITY_HARDENING.md`](R5_0_3_SECURITY_HARDENING.md)** — R5.0.3 security hardening and audit remediation log (A1, A2, A4, M3, M4, M6, N1–N4, B4).
* **[`R5_RELEASE_AUDIT.md`](R5_RELEASE_AUDIT.md)** — Internal release audit and local verification checklist.
* **[`api/ENDPOINTS_R5.md`](api/ENDPOINTS_R5.md)** — R5 REST API additions.
* **[`LOCAL_SETUP_MAC.md`](LOCAL_SETUP_MAC.md)** & **[`LOCAL_TEST_PLAN.md`](LOCAL_TEST_PLAN.md)** — Local macOS Docker + Mailpit + Ollama setup and QA acceptance plan.
