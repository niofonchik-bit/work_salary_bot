from __future__ import annotations

from datetime import datetime

from app.database.models import WorkBreak, WorkSession
from app.repositories.audit import AuditRepository
from app.repositories.sessions import SessionRepository


class WorkTimeUseCase:
    def __init__(self, sessions: SessionRepository, audit: AuditRepository):
        self.sessions = sessions
        self.audit = audit

    async def start(
        self,
        user_id: int,
        started_at_utc: datetime,
        source: str = "telegram",
    ) -> WorkSession:
        # начало смены
        if source not in {"telegram", "geofence"}:
            raise ValueError("Неизвестный источник смены.")
        session = await self.sessions.start(user_id, started_at_utc)
        await self.audit.add(
            user_id,
            "work_session",
            session.id,
            "start",
            after_data={
                "started_at_utc": session.started_at_utc.isoformat(),
                "source": source,
            },
        )
        return session

    async def finish(
        self,
        user_id: int,
        ended_at_utc: datetime,
        source: str = "telegram",
    ) -> WorkSession:
        # завершение смены
        if source not in {"telegram", "geofence"}:
            raise ValueError("Неизвестный источник смены.")

        session = await self.sessions.finish(user_id, ended_at_utc)

        await self.audit.add(
            user_id,
            "work_session",
            session.id,
            "finish",
            after_data={
                "ended_at_utc": ended_at_utc.isoformat(),
                "source": source,
            },
        )

        return session

    async def add_completed(
        self,
        user_id: int,
        started_at_utc: datetime,
        ended_at_utc: datetime,
        source: str = "telegram",
    ) -> WorkSession:
        # создание смены
        if source not in {"telegram", "geofence"}:
            raise ValueError("Неизвестный источник смены.")
        session = await self.sessions.add_manual(user_id, started_at_utc, ended_at_utc)
        await self.audit.add(
            user_id,
            "work_session",
            session.id,
            "create",
            after_data={
                "started_at_utc": session.started_at_utc.isoformat(),
                "ended_at_utc": session.ended_at_utc.isoformat() if session.ended_at_utc else None,
                "source": source,
            },
        )
        return session

    async def start_break(self, user_id: int, started_at_utc: datetime) -> WorkBreak:
        value = await self.sessions.start_break(user_id, started_at_utc)
        await self.audit.add(user_id, "work_break", value.id, "start")
        return value

    async def finish_break(self, user_id: int, ended_at_utc: datetime) -> WorkBreak:
        value = await self.sessions.finish_break(user_id, ended_at_utc)
        await self.audit.add(user_id, "work_break", value.id, "finish")
        return value

    async def delete(self, user_id: int, session_id: int) -> WorkSession:
        value = await self.sessions.soft_delete(user_id, session_id)
        await self.audit.add(user_id, "work_session", session_id, "delete")
        return value

    async def restore_last(self, user_id: int) -> WorkSession:
        session_id = await self.audit.last_deleted_session_id(user_id)
        if session_id is None:
            raise LookupError("Удалённая смена не найдена.")
        value = await self.sessions.restore(user_id, session_id)
        await self.audit.add(user_id, "work_session", session_id, "restore")
        return value
