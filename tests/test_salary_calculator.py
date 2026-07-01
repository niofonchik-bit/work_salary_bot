from datetime import UTC, datetime
from decimal import Decimal

from app.database.models import MonthlySettings, UserSettings, WorkSession
from app.services.salary_calculator import (
    calculate_hourly_rate_cents,
    calculate_month_analysis,
    calculate_standard_minutes,
    summarize_sessions,
)


def make_user(**overrides):
    values = {
        "telegram_id": 1,
        "timezone": "Europe/Istanbul",
        "workday_minutes": 480,
        "default_salary_cents": 2_610_000,
        "default_bonus_cents": 3_480_000,
        "default_target_cents": 8_000_000,
        "overtime_mode": "total",
        "custom_rate_cents": 0,
        "weekend_multiplier": 1.0,
    }
    values.update(overrides)
    return UserSettings(**values)


def make_month(**overrides):
    values = {
        "user_id": 1,
        "year": 2026,
        "month": 7,
        "salary_cents": 2_610_000,
        "bonus_cents": 3_480_000,
        "target_cents": 8_000_000,
        "standard_minutes": 10_080,
    }
    values.update(overrides)
    return MonthlySettings(**values)


def make_session(start: datetime, end: datetime, break_minutes: int = 0, session_id: int = 1):
    return WorkSession(
        id=session_id,
        user_id=1,
        started_at_utc=start,
        ended_at_utc=end,
        break_minutes=break_minutes,
        created_at_utc=start,
        updated_at_utc=end,
    )


def test_auto_standard_minutes_for_july_2026():
    assert calculate_standard_minutes(2026, 7, 480, None) == 184 * 60


def test_hourly_rate_from_total_income_for_168_hours():
    rate = calculate_hourly_rate_cents(make_user(), make_month(), 168 * 60)
    assert rate == Decimal("36250")


def test_multiple_sessions_in_one_day_share_daily_regular_limit():
    sessions = [
        make_session(
            datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
            datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            session_id=1,
        ),
        make_session(
            datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
            datetime(2026, 7, 1, 16, 0, tzinfo=UTC),
            session_id=2,
        ),
    ]

    totals = summarize_sessions(sessions, "Europe/Istanbul", 480)

    assert totals.total_minutes == 600
    assert totals.regular_minutes == 480
    assert totals.weekday_overtime_minutes == 120
    assert totals.weekend_minutes == 0


def test_month_forecast_adds_recorded_weekday_overtime():
    session = make_session(
        datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
        datetime(2026, 7, 1, 15, 0, tzinfo=UTC),
    )

    analysis = calculate_month_analysis(
        make_user(),
        make_month(),
        [session],
        datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
    )

    assert analysis.totals.regular_minutes == 480
    assert analysis.totals.weekday_overtime_minutes == 120
    assert analysis.overtime_income_cents == 72_500
    assert analysis.forecast_income_cents == 6_162_500
    assert analysis.target_gap_cents == 1_837_500


def test_weekend_multiplier_applies_to_all_weekend_minutes():
    session = make_session(
        datetime(2026, 7, 4, 5, 0, tzinfo=UTC),
        datetime(2026, 7, 4, 13, 0, tzinfo=UTC),
    )

    analysis = calculate_month_analysis(
        make_user(weekend_multiplier=2.0),
        make_month(),
        [session],
        datetime(2026, 7, 4, 18, 0, tzinfo=UTC),
    )

    assert analysis.totals.weekend_minutes == 480
    assert analysis.overtime_income_cents == 580_000
    assert analysis.forecast_income_cents == 6_670_000


def test_schedule_marks_gap_as_uncovered_when_month_has_no_days_left():
    analysis = calculate_month_analysis(
        make_user(),
        make_month(),
        [],
        datetime(2026, 7, 31, 23, 0, tzinfo=UTC),
    )

    assert analysis.remaining_weekdays == 0
    assert analysis.available_saturdays == 0
    assert all(option.uncovered_cents == 1_910_000 for option in analysis.schedule_options)
