"""Pure scheduling & timezone calculation rules.

All weekly schedule configurations are naive local wall-clock times; all booked
appointment intervals are timezone-aware and persisted in UTC.

DST Policy (R4.2.1+): Nonexistent local times (spring-forward gaps) and ambiguous
local times (fall-back folds that occur twice) are rejected rather than silently
guessed. See docs/scheduling/DST_POLICY.md.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class WeeklyWindow:
    weekday: int
    opens_at: time | None
    closes_at: time | None
    is_closed: bool = False


@dataclass(frozen=True)
class WeeklyBreak:
    weekday: int
    starts_at: time
    ends_at: time


def valid_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Invalid IANA timezone: {name}")


def interval_fits_schedule(
    starts_at_utc: datetime,
    ends_at_utc: datetime,
    timezone_name: str,
    hours: list[WeeklyWindow],
    breaks: list[WeeklyBreak] | None = None,
) -> bool:
    """Return True if the full interval fits inside an open window without crossing breaks.

    Appointments crossing local midnight are rejected so DST transitions and daily
    closing boundaries remain explicit.
    """
    if starts_at_utc.tzinfo is None or ends_at_utc.tzinfo is None:
        return False
    if ends_at_utc <= starts_at_utc:
        return False
    zone = valid_timezone(timezone_name)
    local_start = starts_at_utc.astimezone(zone)
    local_end = ends_at_utc.astimezone(zone)
    if local_start.date() != local_end.date():
        return False
    weekday = local_start.weekday()
    window = next((h for h in hours if h.weekday == weekday), None)
    if not window or window.is_closed or not window.opens_at or not window.closes_at:
        return False
    start_clock, end_clock = local_start.timetz().replace(tzinfo=None), local_end.timetz().replace(tzinfo=None)
    if start_clock < window.opens_at or end_clock > window.closes_at:
        return False
    for pause in breaks or []:
        if pause.weekday == weekday and start_clock < pause.ends_at and end_clock > pause.starts_at:
            return False
    return True


def local_slot_to_utc(day: date, clock: time, timezone_name: str) -> datetime | None:
    """Unambiguously convert a local wall-clock time to UTC.

    Returns None if the local time does not exist (spring-forward gap) or is
    ambiguous (fall-back fold occurring twice).
    """
    zone = valid_timezone(timezone_name)
    naive = datetime.combine(day, clock)
    candidates = set()
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        # Valid only if round-tripping back to local time yields the exact same wall clock.
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if len(candidates) != 1:
        return None
    return candidates.pop()


def is_ambiguous_local(day: date, clock: time, timezone_name: str) -> bool:
    """Return True if the local wall-clock time occurs twice (DST fall-back)."""
    zone = valid_timezone(timezone_name)
    naive = datetime.combine(day, clock)
    valid = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            valid.add(utc)
    return len(valid) == 2


def iter_local_slots(day: date, opens_at: time, closes_at: time, step_minutes: int):
    cursor = datetime.combine(day, opens_at)
    finish = datetime.combine(day, closes_at)
    step = timedelta(minutes=step_minutes)
    while cursor < finish:
        yield cursor.time()
        cursor += step
