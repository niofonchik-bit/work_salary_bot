from datetime import date, time

import pytest

from app.database.models import CalendarDay, MonthlySettings, PayProfile, UserSettings


@pytest.fixture
def user() -> UserSettings:
    return UserSettings(
        telegram_id=1,
        timezone="Europe/Istanbul",
        workday_minutes=480,
        work_start_time=time(9, 0),
        default_target_cents=8_000_000,
        max_weekday_overtime_minutes=120,
        max_saturdays=2,
        saturday_minutes=480,
        allow_sunday=False,
    )


@pytest.fixture
def profile() -> PayProfile:
    return PayProfile(
        user_id=1,
        salary_cents=2_610_000,
        bonus_cents=3_480_000,
        overtime_rule="balance",
        rate_basis="total",
        custom_rate_cents=0,
        underwork_mode="ignore",
        weekday_multiplier_percent=100,
        saturday_multiplier_percent=100,
        sunday_multiplier_percent=100,
        holiday_multiplier_percent=200,
        rounding_minutes=1,
    )


@pytest.fixture
def month() -> MonthlySettings:
    return MonthlySettings(
        user_id=1,
        year=2026,
        month=7,
        target_cents=8_000_000,
        standard_minutes_override=None,
    )


def make_calendar_day(value: date, expected: int = 480, day_type: str = "workday", paid: bool = True):
    return CalendarDay(
        id=value.toordinal(),
        user_id=1,
        work_date=value,
        day_type=day_type,
        expected_minutes=expected,
        is_paid=paid,
        comment=None,
    )
