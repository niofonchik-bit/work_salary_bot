from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.database.models import MonthlySettings, UserSettings, WorkSession
from app.utils.formatters import count_weekdays


@dataclass(slots=True)
class WorkTotals:
    total_minutes: int
    regular_minutes: int
    weekday_overtime_minutes: int
    weekend_minutes: int
    open_sessions: int


@dataclass(slots=True)
class ScheduleOption:
    requested_saturdays: int
    saturday_count: int
    saturday_minutes_each: int
    weekday_minutes_each: int
    remaining_weekdays: int
    uncovered_cents: int


@dataclass(slots=True)
class MonthAnalysis:
    year: int
    month: int
    standard_minutes: int
    elapsed_standard_minutes: int
    remaining_weekdays: int
    available_saturdays: int
    totals: WorkTotals
    balance_minutes: int
    fixed_income_cents: int
    hourly_rate_cents: Decimal
    overtime_income_cents: int
    accrued_income_cents: int
    forecast_income_cents: int
    target_cents: int
    target_gap_cents: int
    weekday_minutes_to_target: int
    saturday_minutes_to_target: int
    schedule_options: list[ScheduleOption]


def calculate_standard_minutes(
    year: int,
    month: int,
    workday_minutes: int,
    override_minutes: int | None,
) -> int:
    if override_minutes is not None:
        return override_minutes
    return count_weekdays(year, month) * workday_minutes


def calculate_hourly_rate_cents(
    user: UserSettings,
    month_settings: MonthlySettings,
    standard_minutes: int,
) -> Decimal:
    if user.overtime_mode == "custom":
        return Decimal(user.custom_rate_cents)

    basis = month_settings.salary_cents
    if user.overtime_mode == "total":
        basis += month_settings.bonus_cents

    standard_hours = Decimal(standard_minutes) / Decimal(60)
    if standard_hours <= 0:
        return Decimal(0)
    return Decimal(basis) / standard_hours


def summarize_sessions(
    sessions: list[WorkSession],
    timezone_name: str,
    workday_minutes: int,
    now_utc: datetime | None = None,
) -> WorkTotals:
    now_utc = now_utc or datetime.now(UTC)
    zone = ZoneInfo(timezone_name)
    daily_minutes: dict[date, int] = defaultdict(int)
    open_sessions = 0

    for session in sessions:
        end = session.ended_at_utc or now_utc
        if session.ended_at_utc is None:
            open_sessions += 1
        duration = max(0, int(round((end - session.started_at_utc).total_seconds() / 60)))
        duration = max(0, duration - session.break_minutes)
        local_day = session.started_at_utc.astimezone(zone).date()
        daily_minutes[local_day] += duration

    regular = 0
    weekday_overtime = 0
    weekend = 0
    for day, duration in daily_minutes.items():
        if day.weekday() < 5:
            regular += min(duration, workday_minutes)
            weekday_overtime += max(0, duration - workday_minutes)
        else:
            weekend += duration

    return WorkTotals(
        total_minutes=sum(daily_minutes.values()),
        regular_minutes=regular,
        weekday_overtime_minutes=weekday_overtime,
        weekend_minutes=weekend,
        open_sessions=open_sessions,
    )


def calculate_month_analysis(
    user: UserSettings,
    month_settings: MonthlySettings,
    sessions: list[WorkSession],
    now_local: datetime,
) -> MonthAnalysis:
    standard_minutes = calculate_standard_minutes(
        month_settings.year,
        month_settings.month,
        user.workday_minutes,
        month_settings.standard_minutes,
    )
    hourly_rate = calculate_hourly_rate_cents(user, month_settings, standard_minutes)
    totals = summarize_sessions(
        sessions,
        user.timezone,
        user.workday_minutes,
        now_local.astimezone(UTC),
    )

    fixed_income = month_settings.salary_cents + month_settings.bonus_cents
    accrued_fixed = _round_cents(
        Decimal(fixed_income)
        * Decimal(min(totals.regular_minutes, standard_minutes))
        / Decimal(standard_minutes or 1)
    )
    weekday_overtime_income = Decimal(totals.weekday_overtime_minutes) / Decimal(60) * hourly_rate
    weekend_income = (
        Decimal(totals.weekend_minutes) / Decimal(60) * hourly_rate * Decimal(str(user.weekend_multiplier))
    )
    overtime_income = _round_cents(weekday_overtime_income + weekend_income)

    accrued_income = accrued_fixed + overtime_income
    forecast_income = fixed_income + overtime_income
    gap = max(0, month_settings.target_cents - forecast_income)

    weekday_rate_per_minute = hourly_rate / Decimal(60) if hourly_rate > 0 else Decimal(0)
    saturday_rate_per_minute = weekday_rate_per_minute * Decimal(str(user.weekend_multiplier))
    weekday_minutes_to_target = _ceil_minutes(gap, weekday_rate_per_minute)
    saturday_minutes_to_target = _ceil_minutes(gap, saturday_rate_per_minute)

    elapsed_standard = _elapsed_standard_minutes(
        month_settings.year,
        month_settings.month,
        user.workday_minutes,
        now_local.date(),
    )
    balance = totals.total_minutes - elapsed_standard
    remaining_weekdays = _remaining_weekdays(
        month_settings.year,
        month_settings.month,
        now_local.date(),
    )
    available_saturdays = _remaining_saturdays(
        month_settings.year,
        month_settings.month,
        now_local.date(),
    )

    options = [
        _build_schedule_option(
            gap,
            requested_saturdays,
            available_saturdays,
            remaining_weekdays,
            weekday_rate_per_minute,
            saturday_rate_per_minute,
            user.workday_minutes,
        )
        for requested_saturdays in (0, 2, 4)
    ]

    return MonthAnalysis(
        year=month_settings.year,
        month=month_settings.month,
        standard_minutes=standard_minutes,
        elapsed_standard_minutes=elapsed_standard,
        remaining_weekdays=remaining_weekdays,
        available_saturdays=available_saturdays,
        totals=totals,
        balance_minutes=balance,
        fixed_income_cents=fixed_income,
        hourly_rate_cents=hourly_rate,
        overtime_income_cents=overtime_income,
        accrued_income_cents=accrued_income,
        forecast_income_cents=forecast_income,
        target_cents=month_settings.target_cents,
        target_gap_cents=gap,
        weekday_minutes_to_target=weekday_minutes_to_target,
        saturday_minutes_to_target=saturday_minutes_to_target,
        schedule_options=options,
    )


def _build_schedule_option(
    gap_cents: int,
    requested_saturdays: int,
    available_saturdays: int,
    remaining_weekdays: int,
    weekday_rate_per_minute: Decimal,
    saturday_rate_per_minute: Decimal,
    saturday_capacity_minutes: int,
) -> ScheduleOption:
    saturday_count = min(requested_saturdays, available_saturdays)
    if gap_cents <= 0:
        return ScheduleOption(
            requested_saturdays=requested_saturdays,
            saturday_count=saturday_count,
            saturday_minutes_each=0,
            weekday_minutes_each=0,
            remaining_weekdays=remaining_weekdays,
            uncovered_cents=0,
        )

    if saturday_count == 0 or saturday_rate_per_minute <= 0:
        weekday_minutes_each = _ceil_div_minutes(
            Decimal(gap_cents), weekday_rate_per_minute, remaining_weekdays
        )
        uncovered_cents = gap_cents if weekday_minutes_each == 0 else 0
        return ScheduleOption(
            requested_saturdays=requested_saturdays,
            saturday_count=0,
            saturday_minutes_each=0,
            weekday_minutes_each=weekday_minutes_each,
            remaining_weekdays=remaining_weekdays,
            uncovered_cents=uncovered_cents,
        )

    total_saturday_capacity = saturday_count * saturday_capacity_minutes
    saturday_minutes_needed = _ceil_minutes(gap_cents, saturday_rate_per_minute)
    used_saturday_minutes = min(total_saturday_capacity, saturday_minutes_needed)
    saturday_minutes_each = _ceil_int(Decimal(used_saturday_minutes) / Decimal(saturday_count))
    saturday_income = Decimal(used_saturday_minutes) * saturday_rate_per_minute
    remaining_gap = max(Decimal(0), Decimal(gap_cents) - saturday_income)
    weekday_minutes_each = _ceil_div_minutes(
        remaining_gap,
        weekday_rate_per_minute,
        remaining_weekdays,
    )
    uncovered_cents = 0
    if remaining_gap > 0 and weekday_minutes_each == 0:
        uncovered_cents = _round_cents(remaining_gap)

    return ScheduleOption(
        requested_saturdays=requested_saturdays,
        saturday_count=saturday_count,
        saturday_minutes_each=saturday_minutes_each,
        weekday_minutes_each=weekday_minutes_each,
        remaining_weekdays=remaining_weekdays,
        uncovered_cents=uncovered_cents,
    )


def _elapsed_standard_minutes(
    year: int,
    month: int,
    workday_minutes: int,
    today: date,
) -> int:
    if (today.year, today.month) < (year, month):
        return 0
    last_day = calendar.monthrange(year, month)[1]
    end_day = last_day if (today.year, today.month) > (year, month) else min(today.day, last_day)
    weekdays = sum(1 for day in range(1, end_day + 1) if date(year, month, day).weekday() < 5)
    return weekdays * workday_minutes


def _remaining_weekdays(year: int, month: int, today: date) -> int:
    if (today.year, today.month) > (year, month):
        return 0
    first_day = 1 if (today.year, today.month) < (year, month) else today.day + 1
    last_day = calendar.monthrange(year, month)[1]
    return sum(1 for day in range(first_day, last_day + 1) if date(year, month, day).weekday() < 5)


def _remaining_saturdays(year: int, month: int, today: date) -> int:
    if (today.year, today.month) > (year, month):
        return 0
    first_day = 1 if (today.year, today.month) < (year, month) else today.day + 1
    last_day = calendar.monthrange(year, month)[1]
    return sum(1 for day in range(first_day, last_day + 1) if date(year, month, day).weekday() == 5)


def _ceil_minutes(cents: int, rate_per_minute: Decimal) -> int:
    if cents <= 0:
        return 0
    if rate_per_minute <= 0:
        return 0
    return _ceil_int(Decimal(cents) / rate_per_minute)


def _ceil_div_minutes(cents: Decimal | int, rate_per_minute: Decimal, days: int) -> int:
    value = Decimal(cents)
    if value <= 0:
        return 0
    if rate_per_minute <= 0 or days <= 0:
        return 0
    return _ceil_int(value / rate_per_minute / Decimal(days))


def _ceil_int(value: Decimal) -> int:
    integral = int(value)
    return integral if value == integral else integral + 1


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
