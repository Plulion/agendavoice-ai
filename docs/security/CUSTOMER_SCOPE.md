# Branch-Scoped Customer Visibility & Privacy Policy (R5.0.3)

## Data Ownership Model

- Customers belong to the **company (`tenant`)** with unique normalized phone number (`uq_customer_tenant_phone`) and optional validated Chilean RUT (`uq_customer_tenant_rut`), preventing duplicate customer records across branches.
- Every customer tracks its origin branch via `home_branch_id` (migration `0005_r422_customer_home_branch`).
- `TENANT_ADMIN` and `SUPER_ADMIN` have visibility across all branches and are the sole roles authorized to edit tenant-global customer profile fields via `PUT /customers/{customer_id}/profile` (deliberate product decision so branch operators cannot overwrite contact data shared across branches).
- Branch-scoped roles (`BRANCH_MANAGER`, `OPERATOR`, `READ_ONLY`) can view a customer in `GET /customers` if and only if:
  1. `customer.home_branch_id` is in the user's authorized `branch_ids`, **or**
  2. The customer has at least one appointment in the user's authorized `branch_ids`.

## Strict Cross-Branch Phone Booking (R5.0.3 Hardening)

- **`POST /customers/resolve-phone` (A1 Fix):** If a queried phone number belongs exclusively to another branch, the API returns a sanitized cross-branch notice (`cross_branch_linked: true`, `requires_admin_review: true`) **without exposing `id`, `name`, `email`, or `home_branch_id`**.
- **`POST /appointments` (A2 Fix):** For any existing customer, the confirmation email is sent **strictly to the email address already stored in the database** (`customer.email`); caller-supplied `customer_email` values are never used to hijack confirmations. For cross-branch bookings, `customer.name` is omitted from the confirmation email body/HTML.
