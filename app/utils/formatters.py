from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONTH_NAMES = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}

MONTH_NAMES_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_money(cents: int | Decimal, show_kopecks: bool = False) -> str:
    value = Decimal(cents) / Decimal(100)
    if show_kopecks and value != value.to_integral_value():
        formatted = f"{value:,.2f}"
    else:
        formatted = f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"
    return formatted.replace(",", " ").replace(".", ",") + " ₽"


def format_rate(cents_per_hour: Decimal) -> str:
    value = (cents_per_hour / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " ₽/ч"


def format_duration(minutes: int, include_sign: bool = False) -> str:
    sign = ""
    if minutes < 0:
        sign = "−"
    elif include_sign and minutes > 0:
        sign = "+"

    absolute = abs(int(minutes))
    hours, rest = divmod(absolute, 60)
    if hours and rest:
        return f"{sign}{hours} ч {rest:02d} мин"
    if hours:
        return f"{sign}{hours} ч"
    return f"{sign}{rest} мин"


def parse_money_to_cents(value: str) -> int:
    normalized = value.strip().lower().replace("₽", "").replace("руб", "")
    normalized = normalized.replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError("Введите сумму числом, например 80000") from error
    if amount < 0:
        raise ValueError("Сумма не может быть отрицательной")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_duration_to_minutes(value: str) -> int:
    normalized = value.strip().lower().replace(" ", "")
    if not normalized:
        raise ValueError("Введите продолжительность")

    if re.fullmatch(r"\d+(?:[.,]\d+)?", normalized):
        hours = Decimal(normalized.replace(",", "."))
        return int((hours * 60).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    time_match = re.fullmatch(r"(?P<hours>\d{1,3}):(?P<minutes>\d{1,2})", normalized)
    if time_match:
        hours = int(time_match.group("hours"))
        minutes = int(time_match.group("minutes"))
        if minutes >= 60:
            raise ValueError("Минуты должны быть меньше 60")
        return hours * 60 + minutes

    text_match = re.fullmatch(
        r"(?:(?P<hours>\d+)ч)?(?:(?P<minutes>\d+)м(?:ин)?)?",
        normalized,
    )
    if text_match and (text_match.group("hours") or text_match.group("minutes")):
        hours = int(text_match.group("hours") or 0)
        minutes = int(text_match.group("minutes") or 0)
        if minutes >= 60:
            raise ValueError("Минуты должны быть меньше 60")
        return hours * 60 + minutes

    raise ValueError("Используйте формат 8, 8:30 или 8ч30м")


def parse_date(value: str, today: date | None = None) -> date:
    today = today or date.today()
    normalized = value.strip()
    for pattern in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d.%m"):
        try:
            parsed = datetime.strptime(normalized, pattern).date()
            if pattern == "%d.%m":
                parsed = parsed.replace(year=today.year)
            return parsed
        except ValueError:
            continue
    raise ValueError("Введите дату в формате ДД.ММ.ГГГГ")


def parse_time(value: str) -> time:
    normalized = value.strip()
    for pattern in ("%H:%M", "%H.%M"):
        try:
            return datetime.strptime(normalized, pattern).time()
        except ValueError:
            continue
    raise ValueError("Введите время в формате ЧЧ:ММ")


def get_zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Неизвестный часовой пояс. Пример: Europe/Istanbul") from error


def month_bounds_utc(year: int, month: int, timezone_name: str) -> tuple[datetime, datetime]:
    zone = get_zoneinfo(timezone_name)
    start_local = datetime(year, month, 1, tzinfo=zone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def day_bounds_utc(day: date, timezone_name: str) -> tuple[datetime, datetime]:
    zone = get_zoneinfo(timezone_name)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def combine_local(day: date, clock: time, timezone_name: str) -> datetime:
    zone = get_zoneinfo(timezone_name)
    return datetime.combine(day, clock, tzinfo=zone)


def count_weekdays(year: int, month: int) -> int:
    return sum(
        1 for day in range(1, calendar.monthrange(year, month)[1] + 1) if date(year, month, day).weekday() < 5
    )


def add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + offset
    return total // 12, total % 12 + 1
