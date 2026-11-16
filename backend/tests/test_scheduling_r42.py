from datetime import date, datetime, time, timezone
import pytest
from pydantic import ValidationError
from app.schemas import ScheduleConfigIn, WeeklyHoursIn, WeeklyBreakIn, BranchIn
from app.modules.scheduling.availability import (
    WeeklyWindow, WeeklyBreak, interval_fits_schedule, local_slot_to_utc,
)


def week(open_days=(0, 1, 2, 3, 4, 5), opens=time(9), closes=time(18)):
    return [WeeklyHoursIn(weekday=day, is_closed=day not in open_days,
        opens_at=None if day not in open_days else opens,
        closes_at=None if day not in open_days else closes) for day in range(7)]


def test_schedule_requires_all_seven_unique_weekdays():
    with pytest.raises(ValidationError):
        ScheduleConfigIn(hours=week()[:6])
    with pytest.raises(ValidationError):
        ScheduleConfigIn(hours=week()[:6] + [week()[0]])


def test_break_must_be_inside_open_window():
    with pytest.raises(ValidationError):
        ScheduleConfigIn(hours=week(), breaks=[WeeklyBreakIn(weekday=0, starts_at=time(8), ends_at=time(9, 30))])
    config = ScheduleConfigIn(hours=week(), breaks=[WeeklyBreakIn(weekday=0, starts_at=time(13), ends_at=time(14))])
    assert len(config.breaks) == 1
    with pytest.raises(ValidationError):
        ScheduleConfigIn(hours=week(), breaks=[
            WeeklyBreakIn(weekday=0, starts_at=time(12), ends_at=time(14)),
            WeeklyBreakIn(weekday=0, starts_at=time(13), ends_at=time(15)),
        ])


def test_branch_timezone_must_be_valid_iana_name():
    with pytest.raises(ValidationError):
        BranchIn(name="Sucursal Centro", timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        WeeklyHoursIn(weekday=0, opens_at="09:00:00+02:00", closes_at="18:00:00+02:00")


def test_interval_fits_branch_hours_and_rejects_break_overlap():
    hours = [WeeklyWindow(0, time(9), time(18), False)]
    breaks = [WeeklyBreak(0, time(13), time(14))]
    good_start = datetime(2027, 1, 4, 14, 30, tzinfo=timezone.utc)  # 11:30 Santiago (UTC-3 in Jan)
    good_end = datetime(2027, 1, 4, 15, 15, tzinfo=timezone.utc)
    pause_start = datetime(2027, 1, 4, 16, 30, tzinfo=timezone.utc)  # 13:30 local
    pause_end = datetime(2027, 1, 4, 17, 15, tzinfo=timezone.utc)
    assert interval_fits_schedule(good_start, good_end, "America/Santiago", hours, breaks)
    assert not interval_fits_schedule(pause_start, pause_end, "America/Santiago", hours, breaks)


def test_interval_must_fit_entire_window_and_not_cross_midnight():
    hours = [WeeklyWindow(0, time(9), time(18), False)]
    starts = datetime(2027, 1, 4, 20, 30, tzinfo=timezone.utc)  # 17:30 local
    ends = datetime(2027, 1, 4, 21, 15, tzinfo=timezone.utc)  # 18:15 local
    assert not interval_fits_schedule(starts, ends, "America/Santiago", hours)
    cross_start = datetime(2027, 1, 4, 23, 30, tzinfo=timezone.utc)
    cross_end = datetime(2027, 1, 5, 0, 30, tzinfo=timezone.utc)
    assert not interval_fits_schedule(cross_start, cross_end, "America/Santiago", hours)


def test_local_slot_conversion_handles_dst_gap():
    # 00:30 no existe en Santiago el día de inicio del horario de verano 2026.
    assert local_slot_to_utc(date(2026, 9, 6), time(0, 30), "America/Santiago") is None
    assert local_slot_to_utc(date(2026, 9, 6), time(2, 0), "America/Santiago") is not None
