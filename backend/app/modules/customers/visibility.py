"""Pure branch-scoped customer visibility and privacy-safe cross-branch resolution rules (R5.0.3).

A customer is visible in general directory listings (GET /customers) if:
- the user has tenant-wide access (None: TENANT_ADMIN or SUPER_ADMIN), or
- the customer's origin branch (home_branch_id) is among the user's allowed branches, or
- the customer has at least one appointment in one of the user's allowed branches.

Strict Cross-Branch Privacy (R5.0.3 / A1 remediation):
- POST /customers/resolve-phone NEVER returns id, name, email, or home_branch_id
  for a customer belonging exclusively to another branch.
- Booking via POST /appointments with exact phone number sends the confirmation link
  strictly to the customer's stored email address without disclosing their name or
  history to the requesting branch.
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


def sanitize_cross_branch_customer(phone: str) -> dict:
    """Return a privacy-preserving cross-branch notice without exposing customer id,
    name, email, home_branch_id, or visit history from other branches.
    """
    return {
        "cross_branch_linked": True,
        "requires_admin_review": True,
        "phone": normalize_phone(phone) or phone.strip(),
        "detail": (
            "Existing company customer from another branch; personal details are hidden. "
            "Book directly via POST /appointments using phone confirmation or request administrator review."
        ),
    }
