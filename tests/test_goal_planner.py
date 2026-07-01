from datetime import date
from decimal import Decimal

from app.services.goal_planner import build_goal_plan
from tests.conftest import make_calendar_day


def test_goal_plan_respects_limits(user) -> None:
    days = [
        make_calendar_day(date(2026, 7, 6)),
        make_calendar_day(date(2026, 7, 7)),
        make_calendar_day(date(2026, 7, 11), expected=0, day_type="weekend", paid=False),
    ]

    result = build_goal_plan(
        gap_cents=7_000,
        user=user,
        remaining_days=days,
        weekday_rate_per_minute=Decimal("10"),
        saturday_rate_per_minute=Decimal("10"),
        sunday_rate_per_minute=Decimal("10"),
    )

    assert result.achievable
    assert result.weekend_minutes_total <= user.saturday_minutes
    assert all(
        item.minutes <= user.max_weekday_overtime_minutes for item in result.items if item.kind == "weekday"
    )


def test_goal_plan_reports_uncovered_amount(user) -> None:
    user.max_saturdays = 0
    user.max_weekday_overtime_minutes = 10
    days = [make_calendar_day(date(2026, 7, 6))]

    result = build_goal_plan(
        gap_cents=100_000,
        user=user,
        remaining_days=days,
        weekday_rate_per_minute=Decimal("10"),
        saturday_rate_per_minute=Decimal("10"),
        sunday_rate_per_minute=Decimal("10"),
    )

    assert not result.achievable
    assert result.uncovered_cents == 99_900
