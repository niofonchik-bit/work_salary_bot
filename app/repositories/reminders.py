from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import Database
from app.database.tables import ReminderDeliveryTable


class ReminderRepository:
    def __init__(self, database: Database):
        self.database = database

    async def was_sent(self, user_id: int, reminder_type: str, delivery_key: str) -> bool:
        async with self.database.sessions()() as session:
            value = await session.scalar(
                select(ReminderDeliveryTable.id).where(
                    ReminderDeliveryTable.user_id == user_id,
                    ReminderDeliveryTable.reminder_type == reminder_type,
                    ReminderDeliveryTable.delivery_key == delivery_key,
                )
            )
            return value is not None

    async def mark_sent(self, user_id: int, reminder_type: str, delivery_key: str) -> bool:
        # регистрация доставки
        async with self.database.sessions()() as session:
            session.add(
                ReminderDeliveryTable(
                    user_id=user_id,
                    reminder_type=reminder_type,
                    delivery_key=delivery_key,
                    sent_at_utc=datetime.now(UTC),
                )
            )
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False
