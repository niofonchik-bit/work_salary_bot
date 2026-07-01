from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import select

from app.database.enums import DayType
from app.database.models import CalendarDay
from app.database.session import Database
from app.database.tables import CalendarDayTable
from app.repositories.mappers import to_calendar_day


class CalendarRepository:
    def __init__(self, database: Database):
        self.database = database

    async def ensure_month(self, user_id: int, year: int, month: int, workday_minutes: int) -> None:
        # календарь месяца
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        async with self.database.sessions()() as session:
            result = await session.scalars(
                select(CalendarDayTable.work_date).where(
                    CalendarDayTable.user_id == user_id,
                    CalendarDayTable.work_date.between(first, last),
                )
            )
            existing = set(result.all())
            rows: list[CalendarDayTable] = []
            current = first
            while current <= last:
                if current not in existing:
                    is_workday = current.weekday() < 5
                    rows.append(
                        CalendarDayTable(
                            user_id=user_id,
                            work_date=current,
                            day_type=DayType.WORKDAY if is_workday else DayType.WEEKEND,
                            expected_minutes=workday_minutes if is_workday else 0,
                            is_paid=is_workday,
                        )
                    )
                current = current.fromordinal(current.toordinal() + 1)
            if rows:
                session.add_all(rows)
                await session.commit()

    async def get_range(self, user_id: int, start: date, end: date) -> list[CalendarDay]:
        async with self.database.sessions()() as session:
            result = await session.scalars(
                select(CalendarDayTable)
                .where(
                    CalendarDayTable.user_id == user_id,
                    CalendarDayTable.work_date.between(start, end),
                )
                .order_by(CalendarDayTable.work_date)
            )
            return [to_calendar_day(row) for row in result.all()]

    async def get_day(self, user_id: int, value: date) -> CalendarDay | None:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(CalendarDayTable).where(
                    CalendarDayTable.user_id == user_id,
                    CalendarDayTable.work_date == value,
                )
            )
            return to_calendar_day(row) if row else None

    async def set_day(
        self,
        user_id: int,
        value: date,
        day_type: str,
        expected_minutes: int,
        is_paid: bool,
        comment: str | None = None,
    ) -> CalendarDay:
        # настройка дня
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(CalendarDayTable).where(
                    CalendarDayTable.user_id == user_id,
                    CalendarDayTable.work_date == value,
                )
            )
            if row is None:
                row = CalendarDayTable(user_id=user_id, work_date=value)
                session.add(row)
            row.day_type = day_type
            row.expected_minutes = expected_minutes
            row.is_paid = is_paid
            row.comment = comment
            await session.commit()
            await session.refresh(row)
            return to_calendar_day(row)
