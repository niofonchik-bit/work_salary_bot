from datetime import date

from app.database.models import PaySchedule
from app.services.payments import resolve_payment_date


def test_last_workday_payment() -> None:
    schedule = PaySchedule(
        id=1,
        user_id=1,
        title="Премия",
        day_rule="last_workday",
        fixed_day=None,
        amount_cents=1,
        include_overtime=False,
        enabled=True,
    )

    assert resolve_payment_date(schedule, 2026, 5) == date(2026, 5, 29)
