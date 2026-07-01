from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.database.models import WorkSession

Interval = tuple[datetime, datetime]


def split_work_minutes_by_day(
    sessions: list[WorkSession],
    timezone_name: str,
    now_utc: datetime | None = None,
) -> dict[date, int]:
    # разбивка рабочего времени
    zone = ZoneInfo(timezone_name)
    current_utc = now_utc or datetime.now(UTC)
    result: dict[date, int] = defaultdict(int)

    for session in sessions:
        session_end = session.ended_at_utc or current_utc
        if session_end <= session.started_at_utc:
            continue
        intervals = [(session.started_at_utc, session_end)]
        break_intervals = [
            (item.started_at_utc, item.ended_at_utc or current_utc)
            for item in session.breaks
            if (item.ended_at_utc or current_utc) > item.started_at_utc
        ]
        for work_start, work_end in subtract_intervals(intervals, break_intervals):
            for work_date, minutes in split_interval_by_local_day(work_start, work_end, zone).items():
                result[work_date] += minutes

    return dict(result)


def total_break_minutes(session: WorkSession, now_utc: datetime | None = None) -> int:
    # длительность перерыва
    current_utc = now_utc or datetime.now(UTC)
    total_seconds = 0.0
    for item in session.breaks:
        end = item.ended_at_utc or current_utc
        if end > item.started_at_utc:
            total_seconds += (end - item.started_at_utc).total_seconds()
    return max(0, round(total_seconds / 60))


def session_work_minutes(session: WorkSession, now_utc: datetime | None = None) -> int:
    # длительность смены
    current_utc = now_utc or datetime.now(UTC)
    end = session.ended_at_utc or current_utc
    gross = max(0, round((end - session.started_at_utc).total_seconds() / 60))
    return max(0, gross - total_break_minutes(session, current_utc))


def subtract_intervals(intervals: list[Interval], exclusions: list[Interval]) -> list[Interval]:
    # вычитание интервала
    result = list(intervals)
    for exclusion_start, exclusion_end in sorted(exclusions):
        next_result: list[Interval] = []
        for interval_start, interval_end in result:
            if exclusion_end <= interval_start or exclusion_start >= interval_end:
                next_result.append((interval_start, interval_end))
                continue
            if exclusion_start > interval_start:
                next_result.append((interval_start, min(exclusion_start, interval_end)))
            if exclusion_end < interval_end:
                next_result.append((max(exclusion_end, interval_start), interval_end))
        result = [(start, end) for start, end in next_result if end > start]
    return result


def split_interval_by_local_day(start_utc: datetime, end_utc: datetime, zone: ZoneInfo) -> dict[date, int]:
    # граница локального дня
    result: dict[date, int] = defaultdict(int)
    cursor = start_utc
    while cursor < end_utc:
        local_cursor = cursor.astimezone(zone)
        next_local_date = local_cursor.date() + timedelta(days=1)
        next_midnight_local = datetime.combine(next_local_date, time.min, tzinfo=zone)
        boundary_utc = min(end_utc, next_midnight_local.astimezone(UTC))
        seconds = max(0.0, (boundary_utc - cursor).total_seconds())
        result[local_cursor.date()] += round(seconds / 60)
        cursor = boundary_utc
    return dict(result)


def round_minutes(value: int, step: int) -> int:
    # округление минуты
    if step <= 1:
        return max(0, value)
    quotient, remainder = divmod(max(0, value), step)
    return (quotient + (1 if remainder * 2 >= step else 0)) * step
