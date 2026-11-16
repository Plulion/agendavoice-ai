# Política de cambio de horario (DST) — AgendaVoice AI 4.2.1

Las horas de configuración de sucursales, profesionales y recursos son horas de pared locales.
Las reservas se guardan en UTC (`timestamptz`).

## Regla

- **Hora inexistente** (adelanto de reloj): no se ofrece ni se reserva.
- **Hora ambigua** (atraso de reloj, la hora ocurre dos veces): no se ofrece ni se reserva.
  La versión anterior (4.2.0) elegía la primera ocurrencia en silencio; eso se elimina.

Implementación: `local_slot_to_utc` en `backend/app/modules/scheduling/availability.py` devuelve
`None` salvo que la hora local tenga exactamente una interpretación UTC válida.

## Efecto práctico en Santiago (Chile), 2026

| Fecha | Franja | Tipo | Efecto |
|---|---|---|---|
| sábado 4 abr 2026 | 23:00 a 23:59 | ambigua | Ya no se ofrecen slots (4 de 15 min) |
| domingo 6 sep 2026 | 00:00 a 00:59 | inexistente | Sin slots (ya era así en 4.2.0) |

Para el resto del año el comportamiento no cambia.

## Recomendación operativa

Evitar horarios de apertura o pausas en la franja 23:00-00:59 durante las semanas de cambio de horario.

## Ventana de consulta

La consulta de reservas existentes usa una ventana UTC amplia (día anterior a día siguiente),
porque la medianoche local puede no existir. El solapamiento exacto se valida por intervalo.

## Pendiente de decisión de producto

Permitir que el administrador elija explícitamente la primera o la segunda ocurrencia de una hora
ambigua. Requiere una regla de negocio; no se implementa en 4.2.1.
