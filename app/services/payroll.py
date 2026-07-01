from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.database.enums import DayType, OvertimeRule, RateBasis, UnderworkMode
from app.database.models import CalendarDay, MonthlySettings, PayProfile, UserSettings, WorkSession
from app.services.goal_planner import GoalPlan, build_goal_plan
from app.services.time_tracking import round_minutes, split_work_minutes_by_day


@dataclass(slots=True)
class DailyPayroll:
    work_date: date
    day_type: str
    expected_minutes: int
    worked_minutes: int
    regular_minutes: int
    overtime_minutes: int
    paid_absence_minutes: int
    multiplier_percent: int


@dataclass(slots=True)
class MonthAnalysis:
    year: int
    month: int
    standard_minutes: int
    elapsed_standard_minutes: int
    worked_minutes: int
    regular_minutes: int
    overtime_minutes: int
    special_minutes: int
    paid_absence_minutes: int
    underwork_minutes: int
    balance_minutes: int
    open_sessions: int
    fixed_income_cents: int
    accrued_income_cents: int
    forecast_income_cents: int
    overtime_income_cents: int
    underwork_deduction_cents: int
    hourly_rate_cents: Decimal
    target_cents: int
    target_gap_cents: int
    daily: list[DailyPayroll]
    goal_plan: GoalPlan


def calculate_month_analysis(
    user: UserSettings,
    profile: PayProfile,
    month: MonthlySettings,
    calendar_days: list[CalendarDay],
    sessions: list[WorkSession],
    now_local: datetime,
) -> MonthAnalysis:
    # расчёт месяца
    worked_by_day = {
        work_date: minutes
        for work_date, minutes in split_work_minutes_by_day(
            sessions, user.timezone, now_local.astimezone(UTC)
        ).items()
        if (work_date.year, work_date.month) == (month.year, month.month)
    }
    calendar_map = {item.work_date: item for item in calendar_days}
    calendar_standard = sum(item.expected_minutes for item in calendar_days)
    standard = month.standard_minutes_override or calendar_standard
    hourly_rate = calculate_hourly_rate(profile, standard)
    minute_rate = hourly_rate / Decimal(60) if hourly_rate > 0 else Decimal(0)
    today = now_local.date()

    elapsed_calendar_standard = sum(
        item.expected_minutes for item in calendar_days if item.work_date <= today
    )
    elapsed_standard = _scaled_elapsed_standard(
        standard,
        calendar_standard,
        elapsed_calendar_standard,
    )

    daily: list[DailyPayroll] = []
    special_income = Decimal(0)
    special_minutes = 0
    paid_absence = 0
    daily_weekday_overtime = 0

    all_dates = sorted(set(calendar_map) | set(worked_by_day))
    for work_date in all_dates:
        day = calendar_map.get(work_date)
        day_type = day.day_type if day else _fallback_day_type(work_date)
        expected = day.expected_minutes if day else 0
        worked = round_minutes(worked_by_day.get(work_date, 0), profile.rounding_minutes)
        absence_credit = _paid_absence_credit(day)
        paid_absence += absence_credit

        multiplier = _multiplier_for_day(profile, work_date, day_type, expected)
        if expected > 0:
            regular = min(worked, expected)
            overtime = max(0, worked - expected) if profile.overtime_rule == OvertimeRule.DAILY else 0
            daily_weekday_overtime += overtime
        else:
            regular = 0
            overtime = worked
            special_minutes += worked
            special_income += Decimal(worked) * minute_rate * Decimal(multiplier) / Decimal(100)

        daily.append(
            DailyPayroll(
                work_date=work_date,
                day_type=day_type,
                expected_minutes=expected,
                worked_minutes=worked,
                regular_minutes=regular,
                overtime_minutes=overtime,
                paid_absence_minutes=absence_credit,
                multiplier_percent=multiplier,
            )
        )

    standard_day_work = sum(item.worked_minutes for item in daily if item.expected_minutes > 0)
    effective_required = max(0, standard - paid_absence)
    elapsed_paid_absence = sum(item.paid_absence_minutes for item in daily if item.work_date <= today)
    elapsed_required = max(0, elapsed_standard - elapsed_paid_absence)
    elapsed_standard_work = sum(
        item.worked_minutes for item in daily if item.expected_minutes > 0 and item.work_date <= today
    )

    if profile.overtime_rule == OvertimeRule.DAILY:
        weekday_overtime = daily_weekday_overtime
    elif profile.overtime_rule == OvertimeRule.MONTHLY:
        weekday_overtime = max(0, standard_day_work - effective_required)
    else:
        weekday_overtime = max(0, elapsed_standard_work - elapsed_required)

    weekday_income = (
        Decimal(weekday_overtime) * minute_rate * Decimal(profile.weekday_multiplier_percent) / Decimal(100)
    )
    overtime_income = _round_cents(weekday_income + special_income)
    fixed_income = profile.salary_cents + profile.bonus_cents

    credited_elapsed = min(elapsed_standard_work, elapsed_required) + elapsed_paid_absence
    accrued_fixed = _round_cents(
        Decimal(fixed_income) * Decimal(min(credited_elapsed, standard)) / Decimal(standard or 1)
    )
    underwork = max(0, elapsed_required - elapsed_standard_work)
    deduction = 0
    if profile.underwork_mode == UnderworkMode.DEDUCT:
        deduction = _round_cents(Decimal(underwork) * Decimal(fixed_income) / Decimal(standard or 1))

    forecast = max(0, fixed_income - deduction) + overtime_income
    accrued = accrued_fixed + overtime_income
    total_worked = sum(item.worked_minutes for item in daily)
    balance = total_worked + elapsed_paid_absence - elapsed_standard
    gap = max(0, month.target_cents - forecast)

    remaining_days = [item for item in calendar_days if item.work_date > today]
    goal_plan = build_goal_plan(
        gap_cents=gap,
        user=user,
        remaining_days=remaining_days,
        weekday_rate_per_minute=minute_rate * Decimal(profile.weekday_multiplier_percent) / Decimal(100),
        saturday_rate_per_minute=minute_rate * Decimal(profile.saturday_multiplier_percent) / Decimal(100),
        sunday_rate_per_minute=minute_rate * Decimal(profile.sunday_multiplier_percent) / Decimal(100),
    )

    return MonthAnalysis(
        year=month.year,
        month=month.month,
        standard_minutes=standard,
        elapsed_standard_minutes=elapsed_standard,
        worked_minutes=total_worked,
        regular_minutes=min(standard_day_work, effective_required),
        overtime_minutes=weekday_overtime,
        special_minutes=special_minutes,
        paid_absence_minutes=paid_absence,
        underwork_minutes=underwork,
        balance_minutes=balance,
        open_sessions=sum(1 for item in sessions if item.ended_at_utc is None),
        fixed_income_cents=fixed_income,
        accrued_income_cents=accrued,
        forecast_income_cents=forecast,
        overtime_income_cents=overtime_income,
        underwork_deduction_cents=deduction,
        hourly_rate_cents=hourly_rate,
        target_cents=month.target_cents,
        target_gap_cents=gap,
        daily=daily,
        goal_plan=goal_plan,
    )


def calculate_hourly_rate(profile: PayProfile, standard_minutes: int) -> Decimal:
    # расчёт ставки
    if standard_minutes <= 0:
        return Decimal(0)
    if profile.rate_basis == RateBasis.CUSTOM:
        return Decimal(profile.custom_rate_cents)
    basis = profile.salary_cents
    if profile.rate_basis == RateBasis.TOTAL:
        basis += profile.bonus_cents
    return Decimal(basis) / (Decimal(standard_minutes) / Decimal(60))


def _paid_absence_credit(day: CalendarDay | None) -> int:
    if day is None or not day.is_paid or day.expected_minutes <= 0:
        return 0
    if day.day_type in {DayType.WORKDAY, DayType.SHIFTED_WORKDAY}:
        return 0
    return day.expected_minutes


def _multiplier_for_day(
    profile: PayProfile,
    work_date: date,
    day_type: str,
    expected_minutes: int,
) -> int:
    if day_type == DayType.HOLIDAY:
        return profile.holiday_multiplier_percent
    if expected_minutes > 0:
        return profile.weekday_multiplier_percent
    if work_date.weekday() == 5:
        return profile.saturday_multiplier_percent
    if work_date.weekday() == 6:
        return profile.sunday_multiplier_percent
    return profile.weekday_multiplier_percent


def _fallback_day_type(value: date) -> str:
    return DayType.WORKDAY if value.weekday() < 5 else DayType.WEEKEND


def _scaled_elapsed_standard(total: int, calendar_total: int, calendar_elapsed: int) -> int:
    if calendar_total <= 0:
        return 0
    if total == calendar_total:
        return calendar_elapsed
    return _round_cents(Decimal(total) * Decimal(calendar_elapsed) / Decimal(calendar_total))


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
