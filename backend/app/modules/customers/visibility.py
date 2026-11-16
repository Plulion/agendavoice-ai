"""Regla pura de visibilidad y resolución segura de clientes por sucursal (R4.3.0).

Un cliente es visible en listados generales (GET /customers) para un usuario si:
- el usuario tiene acceso a todas las sucursales (None: TENANT_ADMIN o SUPER_ADMIN), o
- la sucursal de origen del cliente (home_branch_id) está entre sus sucursales, o
- el cliente tiene al menos una reserva en alguna de sus sucursales.

Estándar de industria para agendamiento entre sucursales (Blind Upsert / Exact Phone Match):
- Una sucursal NO puede explorar ni listar clientes de otras sucursales.
- Cuando un cliente llama por teléfono o escribe por WhatsApp a una nueva sucursal B y
  entrega su número exacto (+569...), el sistema normaliza el teléfono y vincula la
  nueva cita al registro único del tenant sin exponer el historial de otras sucursales.
- Una vez creada la cita en la sucursal B, el cliente pasa legítimamente a ser visible en B.
"""
from collections.abc import Iterable
import re


def normalize_phone(phone: str) -> str:
    """Normaliza un número telefónico conservando '+' inicial y dígitos."""
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    # Si viene con 9 dígitos chilenos (ej. 912345678), normaliza a +56912345678
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
    """Devuelve únicamente la ficha mínima necesaria para agendar por teléfono,
    ocultando home_branch_id, correo y citas previas en otras sucursales.
    """
    return {
        "id": int(customer_id),
        "name": name.strip(),
        "phone": normalize_phone(phone) or phone.strip(),
        "cross_branch_linked": True,
    }
