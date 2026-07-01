from datetime import UTC, date, datetime

from app.database.models import WorkSession
from app.services.payroll import calculate_month_analysis
from tests.conftest import make_calendar_day


def make_session(session_id: int, start_hour: int, end_hour: int, day: int) -> WorkSession:
    return WorkSession(
        id=session_id,
        user_id=1,
        started_at_utc=datetime(2026, 7, day, start_hour - 3, tzinfo=UTC),
        ended_at_utc=datetime(2026, 7, day, end_hour - 3, tzinfo=UTC),
        note=None,
        deleted_at_utc=None,
        created_at_utc=datetime(2026, 7, day, start_hour - 3, tzinfo=UTC),
        updated_at_utc=datetime(2026, 7, day, end_hour - 3, tzinfo=UTC),
        breaks=[],
    )


def test_balance_rule_compensates_short_day(user, profile, month) -> None:
    calendar = [make_calendar_day(date(2026, 7, 1)), make_calendar_day(date(2026, 7, 2))]
    sessions = [make_session(1, 8, 18, 1), make_session(2, 8, 14, 2)]

    result = calculate_month_analysis(
        user,
        profile,
        month,
        calendar,
        sessions,
        datetime(2026, 7, 2, 20, 0, tzinfo=UTC).astimezone(),
    )

    assert result.worked_minutes == 960
    assert result.balance_minutes == 0
    assert result.overtime_minutes == 0


def test_daily_rule_keeps_daily_overtime(user, profile, month) -> None:
    profile.overtime_rule = "daily"
    calendar = [make_calendar_day(date(2026, 7, 1)), make_calendar_day(date(2026, 7, 2))]
    sessions = [make_session(1, 8, 18, 1), make_session(2, 8, 14, 2)]

    result = calculate_month_analysis(
        user,
        profile,
        month,
        calendar,
        sessions,
        datetime(2026, 7, 2, 20, 0, tzinfo=UTC).astimezone(),
    )

    assert result.overtime_minutes == 120
    assert result.overtime_income_cents > 0


def test_paid_vacation_removes_underwork(user, profile, month) -> None:
    profile.underwork_mode = "deduct"
    calendar = [
        make_calendar_day(
            date(2026, 7, 1),
            expected=480,
            day_type="vacation",
            paid=True,
        )
    ]

    result = calculate_month_analysis(
        user,
        profile,
        month,
        calendar,
        [],
        datetime(2026, 7, 1, 20, 0, tzinfo=UTC).astimezone(),
    )

    assert result.paid_absence_minutes == 480
    assert result.underwork_minutes == 0
    assert result.underwork_deduction_cents == 0
