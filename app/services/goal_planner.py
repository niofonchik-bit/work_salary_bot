from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from app.database.models import CalendarDay, UserSettings


@dataclass(slots=True)
class GoalPlanItem:
    work_date: date
    minutes: int
    kind: str


@dataclass(slots=True)
class GoalPlan:
    items: list[GoalPlanItem]
    required_cents: int
    planned_cents: int
    uncovered_cents: int
    achievable: bool
    weekday_minutes_total: int
    weekend_minutes_total: int


def build_goal_plan(
    gap_cents: int,
    user: UserSettings,
    remaining_days: list[CalendarDay],
    weekday_rate_per_minute: Decimal,
    saturday_rate_per_minute: Decimal,
    sunday_rate_per_minute: Decimal,
) -> GoalPlan:
    # план достижения цели
    if gap_cents <= 0:
        return GoalPlan([], 0, 0, 0, True, 0, 0)

    remaining = Decimal(gap_cents)
    items: list[GoalPlanItem] = []
    saturdays = [
        item for item in remaining_days if item.work_date.weekday() == 5 and item.expected_minutes == 0
    ]
    sundays = [
        item for item in remaining_days if item.work_date.weekday() == 6 and item.expected_minutes == 0
    ]
    weekdays = [item for item in remaining_days if item.expected_minutes > 0]

    weekend_candidates: list[tuple[CalendarDay, Decimal]] = [
        (item, saturday_rate_per_minute) for item in saturdays[: user.max_saturdays]
    ]
    if user.allow_sunday:
        weekend_candidates.extend((item, sunday_rate_per_minute) for item in sundays)

    for day, rate in weekend_candidates:
        if remaining <= 0 or rate <= 0:
            break
        minutes = min(user.saturday_minutes, _ceil_decimal(remaining / rate))
        if minutes <= 0:
            continue
        items.append(GoalPlanItem(day.work_date, minutes, "weekend"))
        remaining -= Decimal(minutes) * rate

    if remaining > 0 and weekdays and weekday_rate_per_minute > 0:
        max_total = len(weekdays) * user.max_weekday_overtime_minutes
        required_minutes = min(max_total, _ceil_decimal(remaining / weekday_rate_per_minute))
        base, extra = divmod(required_minutes, len(weekdays))
        for index, day in enumerate(weekdays):
            minutes = base + (1 if index < extra else 0)
            minutes = min(minutes, user.max_weekday_overtime_minutes)
            if minutes > 0:
                items.append(GoalPlanItem(day.work_date, minutes, "weekday"))
        planned_weekday_minutes = sum(item.minutes for item in items if item.kind == "weekday")
        remaining -= Decimal(planned_weekday_minutes) * weekday_rate_per_minute

    planned_cents = max(0, gap_cents - max(0, _ceil_decimal(remaining)))
    uncovered = max(0, _ceil_decimal(remaining))
    return GoalPlan(
        items=sorted(items, key=lambda item: item.work_date),
        required_cents=gap_cents,
        planned_cents=planned_cents,
        uncovered_cents=uncovered,
        achievable=uncovered == 0,
        weekday_minutes_total=sum(item.minutes for item in items if item.kind == "weekday"),
        weekend_minutes_total=sum(item.minutes for item in items if item.kind == "weekend"),
    )


def _ceil_decimal(value: Decimal) -> int:
    if value <= 0:
        return 0
    return int(value.to_integral_value(rounding=ROUND_CEILING))
