# Daylight Saving Time (DST) Policy — AgendaVoice AI

Weekly schedules for branches, staff, and resources are configured as naive local wall-clock times (`HH:MM:SS`). Confirmed appointments are persisted in UTC (`TIMESTAMPTZ`).

## Deterministic Conversion Rule

- **Nonexistent local time** (spring-forward gap): Never offered in availability and rejected on booking.
- **Ambiguous local time** (fall-back fold where the same wall-clock hour occurs twice): Never offered in availability and rejected on booking.

Implementation: `local_slot_to_utc()` in `backend/app/modules/scheduling/availability.py` evaluates both `fold=0` and `fold=1` and returns `None` unless the local wall-clock time maps to **exactly one** valid UTC instant.

## Practical Impact in Santiago, Chile (`America/Santiago`), 2026

| Date | Local Window | Transition Type | System Behavior |
| :--- | :--- | :--- | :--- |
| Saturday, Apr 4, 2026 | `23:00` – `23:59` | Ambiguous (clocks fall back) | Slots omitted / rejected (prevents silent 1-hour shift) |
| Sunday, Sep 6, 2026 | `00:00` – `00:59` | Nonexistent (clocks spring forward) | Slots omitted / rejected |
