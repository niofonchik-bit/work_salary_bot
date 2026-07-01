from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time


@dataclass(slots=True)
class UserSettings:
    telegram_id: int
    timezone: str
    workday_minutes: int
    work_start_time: time
    default_target_cents: int
    max_weekday_overtime_minutes: int
    max_saturdays: int
    saturday_minutes: int
    allow_sunday: bool


@dataclass(slots=True)
class PayProfile:
    user_id: int
    salary_cents: int
    bonus_cents: int
    overtime_rule: str
    rate_basis: str
    custom_rate_cents: int
    underwork_mode: str
    weekday_multiplier_percent: int
    saturday_multiplier_percent: int
    sunday_multiplier_percent: int
    holiday_multiplier_percent: int
    rounding_minutes: int


@dataclass(slots=True)
class MonthlySettings:
    user_id: int
    year: int
    month: int
    target_cents: int
    standard_minutes_override: int | None


@dataclass(slots=True)
class CalendarDay:
    id: int
    user_id: int
    work_date: date
    day_type: str
    expected_minutes: int
    is_paid: bool
    comment: str | None


@dataclass(slots=True)
class WorkBreak:
    id: int
    session_id: int
    started_at_utc: datetime
    ended_at_utc: datetime | None


@dataclass(slots=True)
class WorkSession:
    id: int
    user_id: int
    started_at_utc: datetime
    ended_at_utc: datetime | None
    note: str | None
    deleted_at_utc: datetime | None
    created_at_utc: datetime
    updated_at_utc: datetime
    breaks: list[WorkBreak] = field(default_factory=list)


@dataclass(slots=True)
class ReminderSettings:
    user_id: int
    enabled: bool
    arrival_time: time | None
    departure_after_minutes: int | None
    open_shift_time: time | None
    open_break_minutes: int | None
    weekly_report_weekday: int | None
    weekly_report_time: time | None


@dataclass(slots=True)
class PaySchedule:
    id: int
    user_id: int
    title: str
    day_rule: str
    fixed_day: int | None
    amount_cents: int
    include_overtime: bool
    enabled: bool
