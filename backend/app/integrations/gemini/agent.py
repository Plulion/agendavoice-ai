"""Branch-scoped Gemini 2.5 Flash conversational agent (R4.3.0).

Operates strictly inside the authenticated tenant's RLS context (`app.tenant_id`)
and restricts all availability and booking tools to the `branch_id` receiving the
voice call or WhatsApp message.
"""
from __future__ import annotations

from typing import Callable

from app.modules.customers.visibility import normalize_phone


def build_branch_system_prompt(company_name: str, branch_name: str, timezone_name: str) -> str:
    """Build the system instruction scoped exclusively to a single branch."""
    return (
        f"Eres la recepcionista virtual de IA de {company_name}, atendiendo exclusivamente "
        f"la sucursal '{branch_name}' (zona horaria {timezone_name}). "
        "No tienes acceso ni puedes consultar agendas, clientes ni profesionales de otras sucursales. "
        "Usa siempre las herramientas provistas para verificar disponibilidad real en PostgreSQL "
        "y confirmar o cancelar reservas. Sé breve, clara y natural."
    )


def parse_natural_intent(message: str) -> dict:
    """Deterministic fallback intent parser when GEMINI_API_KEY is not set locally."""
    text = (message or "").strip().lower()
    if any(k in text for k in ("cancelar", "anular", "cancel")):
        return {"intent": "cancel"}
    if any(k in text for k in ("reservar", "agendar", "confirmar", "quiero hora", "cita")):
        return {"intent": "book"}
    if any(k in text for k in ("disponibilidad", "hora", "horarios", "disponible", "tienen")):
        return {"intent": "availability"}
    return {"intent": "greeting"}


def run_branch_conversation_turn(
    *,
    company_name: str,
    branch_name: str,
    branch_timezone: str,
    sender_phone: str,
    sender_name: str,
    message: str,
    check_availability_fn: Callable[[], list[dict]],
    book_appointment_fn: Callable[[], dict] | None = None,
) -> dict:
    """Execute a branch-isolated conversational turn (Voice or WhatsApp)."""
    clean_phone = normalize_phone(sender_phone)
    parsed = parse_natural_intent(message)
    intent = parsed["intent"]

    if intent == "book" and book_appointment_fn is not None:
        booking = book_appointment_fn()
        return {
            "intent": "book",
            "branch": branch_name,
            "customer_phone": clean_phone,
            "appointment": booking,
            "reply": (
                f"Perfecto {sender_name}, tu reserva #{booking['id']} en sucursal {branch_name} "
                f"quedó confirmada para {booking['starts_at']}. Te esperamos."
            ),
        }

    if intent in ("availability", "book"):
        slots = check_availability_fn()
        if not slots:
            return {
                "intent": "availability",
                "branch": branch_name,
                "slots": [],
                "reply": (
                    f"Hola {sender_name}, por ahora no encontramos bloques disponibles en "
                    f"la sucursal {branch_name} para esa fecha. ¿Deseas consultar otro día?"
                ),
            }
        preview = ", ".join(s["local_starts_at"][11:16] for s in slots[:4])
        return {
            "intent": "availability",
            "branch": branch_name,
            "slots": slots[:5],
            "reply": (
                f"Hola {sender_name}, en sucursal {branch_name} tenemos disponibilidad a las: "
                f"{preview}. Indícame cuál horario prefieres para confirmar tu reserva."
            ),
        }

    return {
        "intent": "greeting",
        "branch": branch_name,
        "reply": (
            f"Bienvenido a {company_name} ({branch_name}). ¿Qué servicio deseas consultar "
            "o agendar hoy?"
        ),
    }
