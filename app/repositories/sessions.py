from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database.models import WorkBreak, WorkSession
from app.database.session import Database
from app.database.tables import WorkBreakTable, WorkSessionTable
from app.repositories.mappers import to_break, to_session


class SessionRepository:
    def __init__(self, database: Database):
        self.database = database

    async def get_active(self, user_id: int) -> WorkSession | None:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.ended_at_utc.is_(None),
                    WorkSessionTable.deleted_at_utc.is_(None),
                )
            )
            return to_session(row) if row else None

    async def get(self, user_id: int, session_id: int, include_deleted: bool = False) -> WorkSession | None:
        conditions = [WorkSessionTable.id == session_id, WorkSessionTable.user_id == user_id]
        if not include_deleted:
            conditions.append(WorkSessionTable.deleted_at_utc.is_(None))
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable).options(selectinload(WorkSessionTable.breaks)).where(*conditions)
            )
            return to_session(row) if row else None

    async def list_range(self, user_id: int, start_utc: datetime, end_utc: datetime) -> list[WorkSession]:
        async with self.database.sessions()() as session:
            result = await session.scalars(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.deleted_at_utc.is_(None),
                    WorkSessionTable.started_at_utc < end_utc,
                    or_(
                        WorkSessionTable.ended_at_utc.is_(None),
                        WorkSessionTable.ended_at_utc > start_utc,
                    ),
                )
                .order_by(WorkSessionTable.started_at_utc)
            )
            return [to_session(row) for row in result.unique().all()]

    async def start(self, user_id: int, started_at_utc: datetime) -> WorkSession:
        # начало смены
        now = datetime.now(UTC)
        async with self.database.sessions()() as session:
            if await self._has_overlap(session, user_id, started_at_utc, None):
                raise ValueError("Новая смена пересекается с существующей.")
            row = WorkSessionTable(
                user_id=user_id,
                started_at_utc=started_at_utc,
                ended_at_utc=None,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ValueError("Рабочая смена уже открыта.") from error
            await session.refresh(row)
            row.breaks = []
            return to_session(row)

    async def finish(self, user_id: int, ended_at_utc: datetime) -> WorkSession:
        # завершение смены
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.ended_at_utc.is_(None),
                    WorkSessionTable.deleted_at_utc.is_(None),
                )
            )
            if row is None:
                raise LookupError("Открытая смена не найдена.")
            if ended_at_utc <= _as_utc(row.started_at_utc):
                raise ValueError("Время ухода должно быть позже времени прихода.")
            active_break = next((item for item in row.breaks if item.ended_at_utc is None), None)
            if active_break is not None:
                active_break.ended_at_utc = ended_at_utc
            row.ended_at_utc = ended_at_utc
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_session(row)

    async def add_manual(
        self,
        user_id: int,
        started_at_utc: datetime,
        ended_at_utc: datetime,
        note: str | None = None,
    ) -> WorkSession:
        if ended_at_utc <= started_at_utc:
            raise ValueError("Время ухода должно быть позже времени прихода.")
        now = datetime.now(UTC)
        async with self.database.sessions()() as session:
            if await self._has_overlap(session, user_id, started_at_utc, ended_at_utc):
                raise ValueError("Новая смена пересекается с существующей.")
            row = WorkSessionTable(
                user_id=user_id,
                started_at_utc=started_at_utc,
                ended_at_utc=ended_at_utc,
                note=note,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row.breaks = []
            return to_session(row)

    async def update_time(
        self,
        user_id: int,
        session_id: int,
        started_at_utc: datetime,
        ended_at_utc: datetime | None,
    ) -> WorkSession:
        if ended_at_utc is not None and ended_at_utc <= started_at_utc:
            raise ValueError("Время ухода должно быть позже времени прихода.")
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(
                    WorkSessionTable.id == session_id,
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.deleted_at_utc.is_(None),
                )
            )
            if row is None:
                raise LookupError("Смена не найдена.")
            if await self._has_overlap(session, user_id, started_at_utc, ended_at_utc, session_id):
                raise ValueError("Изменённая смена пересекается с существующей.")
            for work_break in row.breaks:
                break_start = _as_utc(work_break.started_at_utc)
                break_end = _as_utc(work_break.ended_at_utc) if work_break.ended_at_utc else None
                if break_start < started_at_utc:
                    raise ValueError("Начало смены не может быть позже существующего перерыва.")
                if ended_at_utc is not None and break_end is not None and break_end > ended_at_utc:
                    raise ValueError("Уход не может быть раньше завершения существующего перерыва.")
            row.started_at_utc = started_at_utc
            row.ended_at_utc = ended_at_utc
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_session(row)

    async def start_break(self, user_id: int, started_at_utc: datetime) -> WorkBreak:
        # начало перерыва
        async with self.database.sessions()() as session:
            work_session = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.ended_at_utc.is_(None),
                    WorkSessionTable.deleted_at_utc.is_(None),
                )
            )
            if work_session is None:
                raise LookupError("Открытая смена не найдена.")
            if any(item.ended_at_utc is None for item in work_session.breaks):
                raise ValueError("Перерыв уже открыт.")
            row = WorkBreakTable(
                session_id=work_session.id,
                started_at_utc=started_at_utc,
                ended_at_utc=None,
                created_at_utc=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return to_break(row)

    async def finish_break(self, user_id: int, ended_at_utc: datetime) -> WorkBreak:
        # завершение перерыва
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkBreakTable)
                .join(WorkSessionTable, WorkSessionTable.id == WorkBreakTable.session_id)
                .where(
                    WorkSessionTable.user_id == user_id,
                    WorkSessionTable.deleted_at_utc.is_(None),
                    WorkBreakTable.ended_at_utc.is_(None),
                )
            )
            if row is None:
                raise LookupError("Открытый перерыв не найден.")
            if ended_at_utc <= _as_utc(row.started_at_utc):
                raise ValueError("Время завершения должно быть позже начала перерыва.")
            row.ended_at_utc = ended_at_utc
            await session.commit()
            return to_break(row)

    async def soft_delete(self, user_id: int, session_id: int) -> WorkSession:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(WorkSessionTable.id == session_id, WorkSessionTable.user_id == user_id)
            )
            if row is None:
                raise LookupError("Смена не найдена.")
            row.deleted_at_utc = datetime.now(UTC)
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_session(row)

    async def restore(self, user_id: int, session_id: int) -> WorkSession:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(WorkSessionTable)
                .options(selectinload(WorkSessionTable.breaks))
                .where(WorkSessionTable.id == session_id, WorkSessionTable.user_id == user_id)
            )
            if row is None:
                raise LookupError("Смена не найдена.")
            if await self._has_overlap(
                session,
                user_id,
                row.started_at_utc,
                row.ended_at_utc,
                session_id,
            ):
                raise ValueError("Восстановленная смена пересекается с существующей.")
            row.deleted_at_utc = None
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_session(row)

    async def _has_overlap(
        self,
        session,
        user_id: int,
        start: datetime,
        end: datetime | None,
        excluded_id: int | None = None,
    ) -> bool:
        effective_end = end or datetime.max.replace(tzinfo=UTC)
        conditions = [
            WorkSessionTable.user_id == user_id,
            WorkSessionTable.deleted_at_utc.is_(None),
            WorkSessionTable.started_at_utc < effective_end,
            or_(WorkSessionTable.ended_at_utc.is_(None), WorkSessionTable.ended_at_utc > start),
        ]
        if excluded_id is not None:
            conditions.append(WorkSessionTable.id != excluded_id)
        return await session.scalar(select(WorkSessionTable.id).where(and_(*conditions)).limit(1)) is not None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
