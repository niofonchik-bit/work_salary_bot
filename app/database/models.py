from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class UserSettings:
    telegram_id: int
    timezone: str
    workday_minutes: int
    default_salary_cents: int
    default_bonus_cents: int
    default_target_cents: int
    overtime_mode: str
    custom_rate_cents: int
    weekend_multiplier: float


@dataclass(slots=True)
class MonthlySettings:
    user_id: int
    year: int
    month: int
    salary_cents: int
    bonus_cents: int
    target_cents: int
    standard_minutes: int | None


@dataclass(slots=True)
class WorkSession:
    id: int
    user_id: int
    started_at_utc: datetime
    ended_at_utc: datetime | None
    break_minutes: int
    created_at_utc: datetime
    updated_at_utc: datetime
