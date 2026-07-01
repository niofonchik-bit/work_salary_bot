from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal

MONTH_NAMES = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)

DAY_TYPE_NAMES = {
    "workday": "рабочий день",
    "weekend": "выходной",
    "holiday": "праздник",
    "vacation": "отпуск",
    "sick_leave": "больничный",
    "unpaid_leave": "неоплачиваемый отпуск",
    "day_off": "отгул",
    "shifted_workday": "перенесённый рабочий день",
}


def format_money(cents: int | Decimal) -> str:
    value = int(Decimal(cents).quantize(Decimal("1")))
    rubles = value // 100
    return f"{rubles:,}".replace(",", " ") + " ₽"


def format_rate(cents: Decimal) -> str:
    rubles = cents / Decimal(100)
    return f"{rubles:.2f}".replace(".", ",") + " ₽/ч"


def format_minutes(minutes: int, signed: bool = False) -> str:
    sign = ""
    if signed:
        sign = "+" if minutes > 0 else "−" if minutes < 0 else ""
    value = abs(minutes)
    hours, remainder = divmod(value, 60)
    if hours and remainder:
        return f"{sign}{hours} ч {remainder} мин"
    if hours:
        return f"{sign}{hours} ч"
    return f"{sign}{remainder} мин"


def format_datetime(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def month_title(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month - 1].capitalize()} {year}"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
