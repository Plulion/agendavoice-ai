"""Pure branch-scoped customer visibility and cross-branch Blind Upsert rules (R4.3.0).

A customer is visible in general directory listings (GET /customers) if:
- the user has tenant-wide access (None: TENANT_ADMIN or SUPER_ADMIN), or
- the customer's origin branch (home_branch_id) is among the user's allowed branches, or
- the customer has at least one appointment in one of the user's allowed branches.

Industry standard for cross-branch telephone/WhatsApp booking (Blind Upsert):
- A branch cannot browse or list customers belonging exclusively to other branches.
- When a customer calls or messages a new branch B and provides their exact phone number (+569...),
  the backend normalizes the phone number and links the new appointment to the single tenant customer
  record without exposing prior history from other branches.
- Once the appointment is booked in branch B, the customer legitimately becomes visible to branch B.
"""
from collections.abc import Iterable
import re


def normalize_phone(phone: str) -> str:
    """Normalize a phone number, preserving a leading '+' and digits."""
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    # Normalize 9-digit Chilean mobile numbers (e.g., 912345678 -> +56912345678)
    if len(digits) == 9 and digits.startswith("9"):
        return f"+56{digits}"
    if len(digits) == 11 and digits.startswith("569"):
        return f"+{digits}"
    return f"+{digits}" if raw.startswith("+") else digits


def customer_visible(allowed_branch_ids: list[int] | None,
                     home_branch_id: int | None,
                     visited_branch_ids: Iterable[int]) -> bool:
    if allowed_branch_ids is None:
        return True
    allowed = set(allowed_branch_ids)
    if not allowed:
        return False
    if home_branch_id is not None and home_branch_id in allowed:
        return True
    return bool(allowed & set(visited_branch_ids))


def sanitize_cross_branch_customer(customer_id: int, name: str, phone: str) -> dict:
    """Return only the minimal customer fields required to complete a phone booking,
    hiding home_branch_id, email, and prior visits at other branches.
    """
    return {
        "id": int(customer_id),
        "name": name.strip(),
        "phone": normalize_phone(phone) or phone.strip(),
        "cross_branch_linked": True,
    }
