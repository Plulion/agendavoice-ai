# Branch-Scoped Customer Visibility & Blind Upsert Policy (R4.3.0)

## Data Ownership Model

- Customers belong to the **company (`tenant`)** with a unique normalized phone number per tenant (`uq_customer_tenant_phone`), preventing duplicate customer records across branches.
- Every customer record tracks its origin branch via `home_branch_id` (added in migration `0005_r422_customer_home_branch`).
- `TENANT_ADMIN` and `SUPER_ADMIN` have visibility across all branches in the company.
- Branch-scoped roles (`BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`) can view a customer in `GET /customers` if and only if:
  1. `customer.home_branch_id` is in the user's authorized `branch_ids`, **or**
  2. The customer has at least one appointment in the user's authorized `branch_ids`.

## Cross-Branch Phone Booking ("Blind Upsert" — R4.3.0)

When a customer originally registered at **Branch A** calls or messages **Branch B** to book an appointment:
- The Branch B operator cannot browse Branch A's customer list.
- However, by providing the customer's exact phone number (`+569...`) to `POST /appointments` (via `customer_phone`) or `POST /customers/resolve-phone`, the backend normalizes the phone number, links the existing tenant customer record under RLS, and creates the appointment in **Branch B** without exposing Branch A's history or metadata.
- Once the appointment is created in Branch B, the customer legitimately becomes visible to Branch B.
