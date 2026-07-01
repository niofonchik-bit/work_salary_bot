from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import MonthlySettings, PayProfile, ReminderSettings, UserSettings
from app.database.session import Database
from app.database.tables import (
    MonthlySettingsTable,
    PayProfileTable,
    PayScheduleTable,
    ReminderSettingsTable,
    UserTable,
)
from app.repositories.mappers import to_month, to_pay_profile, to_reminder_settings, to_user


class UserRepository:
    def __init__(self, database: Database):
        self.database = database

    async def ensure(self, telegram_id: int, timezone_name: str) -> None:
        # профиль пользователя
        now = datetime.now(UTC)
        async with self.database.sessions()() as session:
            if await session.get(UserTable, telegram_id) is None:
                session.add(
                    UserTable(
                        telegram_id=telegram_id,
                        timezone=timezone_name,
                        created_at_utc=now,
                        updated_at_utc=now,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()

        async with self.database.sessions()() as session:
            if await session.get(PayProfileTable, telegram_id) is None:
                session.add(PayProfileTable(user_id=telegram_id, updated_at_utc=now))
            if await session.get(ReminderSettingsTable, telegram_id) is None:
                session.add(ReminderSettingsTable(user_id=telegram_id))

            existing_titles = set(
                await session.scalars(
                    select(PayScheduleTable.title).where(PayScheduleTable.user_id == telegram_id)
                )
            )
            if "Зарплата" not in existing_titles:
                session.add(
                    PayScheduleTable(
                        user_id=telegram_id,
                        title="Зарплата",
                        day_rule="fixed_day",
                        fixed_day=15,
                        amount_cents=2_610_000,
                        include_overtime=False,
                    )
                )
            if "Премия" not in existing_titles:
                session.add(
                    PayScheduleTable(
                        user_id=telegram_id,
                        title="Премия",
                        day_rule="last_day",
                        fixed_day=None,
                        amount_cents=3_480_000,
                        include_overtime=True,
                    )
                )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def get(self, telegram_id: int) -> UserSettings:
        async with self.database.sessions()() as session:
            row = await session.get(UserTable, telegram_id)
            if row is None:
                raise LookupError("Пользователь не инициализирован.")
            return to_user(row)

    async def update(self, telegram_id: int, field: str, value: Any) -> None:
        allowed = {
            "timezone",
            "workday_minutes",
            "work_start_time",
            "default_target_cents",
            "max_weekday_overtime_minutes",
            "max_saturdays",
            "saturday_minutes",
            "allow_sunday",
        }
        if field not in allowed:
            raise ValueError(f"Недоступная настройка пользователя: {field}")
        async with self.database.sessions()() as session:
            row = await session.get(UserTable, telegram_id)
            if row is None:
                raise LookupError("Пользователь не инициализирован.")
            setattr(row, field, value)
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()

    async def get_pay_profile(self, user_id: int) -> PayProfile:
        async with self.database.sessions()() as session:
            row = await session.get(PayProfileTable, user_id)
            if row is None:
                raise LookupError("Профиль оплаты не найден.")
            return to_pay_profile(row)

    async def update_pay_profile(self, user_id: int, field: str, value: Any) -> None:
        allowed = {
            "salary_cents",
            "bonus_cents",
            "overtime_rule",
            "rate_basis",
            "custom_rate_cents",
            "underwork_mode",
            "weekday_multiplier_percent",
            "saturday_multiplier_percent",
            "sunday_multiplier_percent",
            "holiday_multiplier_percent",
            "rounding_minutes",
        }
        if field not in allowed:
            raise ValueError(f"Недоступная настройка оплаты: {field}")
        async with self.database.sessions()() as session:
            row = await session.get(PayProfileTable, user_id)
            if row is None:
                raise LookupError("Профиль оплаты не найден.")
            setattr(row, field, value)
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()

    async def get_month(self, user_id: int, year: int, month: int) -> MonthlySettings:
        key = (user_id, year, month)
        async with self.database.sessions()() as session:
            row = await session.get(MonthlySettingsTable, key)
            if row is None:
                user = await session.get(UserTable, user_id)
                if user is None:
                    raise LookupError("Пользователь не инициализирован.")
                row = MonthlySettingsTable(
                    user_id=user_id,
                    year=year,
                    month=month,
                    target_cents=user.default_target_cents,
                    standard_minutes_override=None,
                )
                session.add(row)
                await session.commit()
            return to_month(row)

    async def update_month(self, user_id: int, year: int, month: int, field: str, value: Any) -> None:
        if field not in {"target_cents", "standard_minutes_override"}:
            raise ValueError(f"Недоступная настройка месяца: {field}")
        await self.get_month(user_id, year, month)
        async with self.database.sessions()() as session:
            row = await session.get(MonthlySettingsTable, (user_id, year, month))
            if row is None:
                raise LookupError("Настройка месяца не найдена.")
            setattr(row, field, value)
            await session.commit()

    async def get_reminder_settings(self, user_id: int) -> ReminderSettings:
        async with self.database.sessions()() as session:
            row = await session.get(ReminderSettingsTable, user_id)
            if row is None:
                row = ReminderSettingsTable(user_id=user_id)
                session.add(row)
                await session.commit()
            return to_reminder_settings(row)

    async def update_reminder_settings(self, user_id: int, field: str, value: Any) -> None:
        allowed = {
            "enabled",
            "arrival_time",
            "departure_after_minutes",
            "open_shift_time",
            "open_break_minutes",
            "weekly_report_weekday",
            "weekly_report_time",
        }
        if field not in allowed:
            raise ValueError(f"Недоступная настройка напоминания: {field}")
        async with self.database.sessions()() as session:
            row = await session.get(ReminderSettingsTable, user_id)
            if row is None:
                row = ReminderSettingsTable(user_id=user_id)
                session.add(row)
            setattr(row, field, value)
            await session.commit()

    async def list_ids(self) -> list[int]:
        from sqlalchemy import select

        async with self.database.sessions()() as session:
            result = await session.scalars(select(UserTable.telegram_id))
            return list(result.all())
