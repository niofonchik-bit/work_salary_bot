from __future__ import annotations

from sqlalchemy import select

from app.database.models import PaySchedule
from app.database.session import Database
from app.database.tables import PayScheduleTable
from app.repositories.mappers import to_pay_schedule


class PaymentRepository:
    def __init__(self, database: Database):
        self.database = database

    async def list(self, user_id: int) -> list[PaySchedule]:
        async with self.database.sessions()() as session:
            result = await session.scalars(
                select(PayScheduleTable)
                .where(PayScheduleTable.user_id == user_id, PayScheduleTable.enabled.is_(True))
                .order_by(PayScheduleTable.id)
            )
            return [to_pay_schedule(row) for row in result.all()]

    async def sync_default_amounts(self, user_id: int, salary_cents: int, bonus_cents: int) -> None:
        # синхронизация выплаты
        async with self.database.sessions()() as session:
            result = await session.scalars(
                select(PayScheduleTable).where(PayScheduleTable.user_id == user_id)
            )
            for row in result.all():
                if row.title == "Зарплата":
                    row.amount_cents = salary_cents
                elif row.title == "Премия":
                    row.amount_cents = bonus_cents
            await session.commit()
