"""Agente conversacional Gemini 2.5 Flash con aislamiento estricto por sucursal (R4.3.0).

Opera siempre dentro del contexto RLS del tenant (`app.tenant_id`) y restringe
todas las herramientas de consulta y agendamiento al `branch_id` de la sucursal
que recibe la llamada o mensaje de WhatsApp.
"""
from __future__ import annotations

from typing import Callable

from app.modules.customers.visibility import normalize_phone


def build_branch_system_prompt(company_name: str, branch_name: str, timezone_name: str) -> str:
    """Construye el system_instruction acotado exclusivamente a una sucursal."""
    return (
        f"Eres la recepcionista virtual de IA de {company_name}, atendiendo exclusivamente "
        f"la sucursal '{branch_name}' (zona horaria {timezone_name}). "
        "No tienes acceso ni puedes consultar agendas, clientes ni profesionales de otras sucursales. "
        "Usa siempre las herramientas provistas para verificar disponibilidad real en PostgreSQL "
        "y confirmar o cancelar reservas. Sé breve, clara y natural."
    )


def parse_natural_intent(message: str) -> dict:
    """Analizador determinista de respaldo cuando GEMINI_API_KEY no está configurada en local."""
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
    """Ejecuta un turno conversacional (Voz o WhatsApp) acotado a la sucursal."""
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
