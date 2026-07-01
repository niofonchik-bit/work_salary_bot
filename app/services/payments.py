from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.database.enums import PaymentDayRule
from app.database.models import PaySchedule


@dataclass(slots=True)
class PaymentForecast:
    title: str
    payment_date: date
    amount_cents: int
    includes_overtime: bool
    is_received: bool


def build_payment_forecast(
    schedules: list[PaySchedule],
    year: int,
    month: int,
    today: date,
    overtime_income_cents: int,
) -> list[PaymentForecast]:
    # прогноз выплаты
    result: list[PaymentForecast] = []
    for schedule in schedules:
        payment_date = resolve_payment_date(schedule, year, month)
        amount = schedule.amount_cents + (overtime_income_cents if schedule.include_overtime else 0)
        result.append(
            PaymentForecast(
                title=schedule.title,
                payment_date=payment_date,
                amount_cents=amount,
                includes_overtime=schedule.include_overtime,
                is_received=payment_date < today,
            )
        )
    return sorted(result, key=lambda item: item.payment_date)


def resolve_payment_date(schedule: PaySchedule, year: int, month: int) -> date:
    # дата выплаты
    last_day = calendar.monthrange(year, month)[1]
    if schedule.day_rule == PaymentDayRule.FIXED_DAY:
        return date(year, month, min(schedule.fixed_day or 1, last_day))
    if schedule.day_rule == PaymentDayRule.LAST_WORKDAY:
        current = date(year, month, last_day)
        while current.weekday() >= 5:
            current -= timedelta(days=1)
        return current
    return date(year, month, last_day)
