from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.database.session import Database
from app.database.tables import AuditEventTable


class AuditRepository:
    def __init__(self, database: Database):
        self.database = database

    async def add(
        self,
        user_id: int,
        entity_type: str,
        entity_id: str | int,
        action: str,
        before_data: dict | None = None,
        after_data: dict | None = None,
    ) -> None:
        # запись аудита
        async with self.database.sessions()() as session:
            session.add(
                AuditEventTable(
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    action=action,
                    before_data=before_data,
                    after_data=after_data,
                    created_at_utc=datetime.now(UTC),
                )
            )
            await session.commit()

    async def last_deleted_session_id(self, user_id: int) -> int | None:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(AuditEventTable)
                .where(
                    AuditEventTable.user_id == user_id,
                    AuditEventTable.entity_type == "work_session",
                    AuditEventTable.action == "delete",
                )
                .order_by(AuditEventTable.created_at_utc.desc())
                .limit(1)
            )
            return int(row.entity_id) if row else None
