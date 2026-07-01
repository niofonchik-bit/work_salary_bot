from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.enums import GeofenceEventStatus, PendingShiftStatus
from app.database.models import GeofenceRegistration, PendingShift
from app.database.session import Database
from app.database.tables import GeofenceEventTable, PendingShiftTable
from app.repositories.mappers import to_geofence_event, to_pending_shift

_PENDING_STATUSES = {
    PendingShiftStatus.WAITING_ARRIVAL,
    PendingShiftStatus.WAITING_DEPARTURE,
    PendingShiftStatus.READY,
    PendingShiftStatus.ATTENTION,
}


class GeofenceRepository:
    def __init__(self, database: Database):
        self.database = database

    async def register_event(
        self,
        user_id: int,
        local_date: date,
        zone: str,
        event_type: str,
        occurred_at_utc: datetime,
        client: str | None,
        dedup_minutes: int,
    ) -> GeofenceRegistration:
        # регистрация события
        for attempt in range(2):
            try:
                return await self._register_event(
                    user_id,
                    local_date,
                    zone,
                    event_type,
                    occurred_at_utc,
                    client,
                    dedup_minutes,
                )
            except IntegrityError:
                if attempt:
                    raise
        raise RuntimeError("Событие геозоны не зарегистрировано.")

    async def _register_event(
        self,
        user_id: int,
        local_date: date,
        zone: str,
        event_type: str,
        occurred_at_utc: datetime,
        client: str | None,
        dedup_minutes: int,
    ) -> GeofenceRegistration:
        now = datetime.now(UTC)
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(PendingShiftTable)
                .where(
                    PendingShiftTable.user_id == user_id,
                    PendingShiftTable.local_date == local_date,
                )
                .with_for_update()
            )
            if row is None:
                row = PendingShiftTable(
                    user_id=user_id,
                    local_date=local_date,
                    suggested_start_utc=None,
                    suggested_end_utc=None,
                    status=PendingShiftStatus.WAITING_DEPARTURE,
                    telegram_chat_id=None,
                    telegram_message_id=None,
                    work_session_id=None,
                    created_at_utc=now,
                    updated_at_utc=now,
                    processed_at_utc=None,
                )
                session.add(row)
                await session.flush()

            processed = row.status in {
                PendingShiftStatus.CONFIRMED,
                PendingShiftStatus.REJECTED,
            }
            event_status = self._merge_event(row, event_type, occurred_at_utc, dedup_minutes, processed)
            if not processed:
                row.status = _derive_status(row.suggested_start_utc, row.suggested_end_utc)
                row.updated_at_utc = now

            event_row = GeofenceEventTable(
                user_id=user_id,
                pending_shift_id=row.id,
                zone=zone,
                event_type=event_type,
                occurred_at_utc=occurred_at_utc,
                client=client or None,
                status=event_status,
                created_at_utc=now,
            )
            session.add(event_row)
            await session.commit()
            await session.refresh(event_row)
            return GeofenceRegistration(
                event=to_geofence_event(event_row),
                pending_shift=to_pending_shift(row),
                duplicate=event_status == GeofenceEventStatus.DUPLICATE or processed,
            )

    @staticmethod
    def _merge_event(
        row: PendingShiftTable,
        event_type: str,
        occurred_at_utc: datetime,
        dedup_minutes: int,
        processed: bool,
    ) -> str:
        if processed:
            return GeofenceEventStatus.DUPLICATE

        if event_type == "arrival":
            current = row.suggested_start_utc
            if current is None:
                row.suggested_start_utc = occurred_at_utc
                return GeofenceEventStatus.RECORDED
            distance = abs((occurred_at_utc - _as_utc(current)).total_seconds()) / 60
            if occurred_at_utc < _as_utc(current):
                row.suggested_start_utc = occurred_at_utc
                return GeofenceEventStatus.MERGED
            return GeofenceEventStatus.DUPLICATE if distance <= dedup_minutes else GeofenceEventStatus.MERGED

        current = row.suggested_end_utc
        if current is None:
            row.suggested_end_utc = occurred_at_utc
            return GeofenceEventStatus.RECORDED
        distance = abs((occurred_at_utc - _as_utc(current)).total_seconds()) / 60
        if occurred_at_utc > _as_utc(current):
            row.suggested_end_utc = occurred_at_utc
            return GeofenceEventStatus.MERGED
        return GeofenceEventStatus.DUPLICATE if distance <= dedup_minutes else GeofenceEventStatus.MERGED

    async def get(self, user_id: int, pending_shift_id: int) -> PendingShift:
        async with self.database.sessions()() as session:
            row = await session.scalar(
                select(PendingShiftTable).where(
                    PendingShiftTable.id == pending_shift_id,
                    PendingShiftTable.user_id == user_id,
                )
            )
            if row is None:
                raise LookupError("Ожидающая смена не найдена.")
            return to_pending_shift(row)

    async def list_pending(self, user_id: int, limit: int = 31) -> list[PendingShift]:
        async with self.database.sessions()() as session:
            rows = await session.scalars(
                select(PendingShiftTable)
                .where(
                    PendingShiftTable.user_id == user_id,
                    PendingShiftTable.status.in_([value.value for value in _PENDING_STATUSES]),
                )
                .order_by(PendingShiftTable.local_date.desc())
                .limit(limit)
            )
            return [to_pending_shift(row) for row in rows]

    async def list_ready(self, user_id: int, limit: int = 31) -> list[PendingShift]:
        async with self.database.sessions()() as session:
            rows = await session.scalars(
                select(PendingShiftTable)
                .where(
                    PendingShiftTable.user_id == user_id,
                    PendingShiftTable.status == PendingShiftStatus.READY,
                )
                .order_by(PendingShiftTable.local_date)
                .limit(limit)
            )
            return [to_pending_shift(row) for row in rows]

    async def update_message(
        self,
        user_id: int,
        pending_shift_id: int,
        chat_id: int,
        message_id: int,
    ) -> PendingShift:
        async with self.database.sessions()() as session:
            row = await self._get_row(session, user_id, pending_shift_id)
            row.telegram_chat_id = chat_id
            row.telegram_message_id = message_id
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_pending_shift(row)

    async def update_time(
        self,
        user_id: int,
        pending_shift_id: int,
        field: str,
        value_utc: datetime,
    ) -> PendingShift:
        async with self.database.sessions()() as session:
            row = await self._get_row(session, user_id, pending_shift_id)
            if row.status not in _PENDING_STATUSES:
                raise ValueError("Смена уже обработана.")
            if field == "start":
                row.suggested_start_utc = value_utc
            elif field == "end":
                row.suggested_end_utc = value_utc
            else:
                raise ValueError("Неизвестное поле времени.")
            row.status = _derive_status(row.suggested_start_utc, row.suggested_end_utc)
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            return to_pending_shift(row)

    async def mark_confirmed(
        self,
        user_id: int,
        pending_shift_id: int,
        work_session_id: int,
    ) -> PendingShift:
        async with self.database.sessions()() as session:
            row = await self._get_row(session, user_id, pending_shift_id)
            if row.status == PendingShiftStatus.CONFIRMED:
                return to_pending_shift(row)
            if row.status == PendingShiftStatus.REJECTED:
                raise ValueError("Смена уже отклонена.")
            row.status = PendingShiftStatus.CONFIRMED
            row.work_session_id = work_session_id
            row.processed_at_utc = datetime.now(UTC)
            row.updated_at_utc = row.processed_at_utc
            await session.commit()
            return to_pending_shift(row)

    async def mark_rejected(self, user_id: int, pending_shift_id: int) -> PendingShift:
        async with self.database.sessions()() as session:
            row = await self._get_row(session, user_id, pending_shift_id)
            if row.status == PendingShiftStatus.CONFIRMED:
                raise ValueError("Смена уже подтверждена.")
            row.status = PendingShiftStatus.REJECTED
            row.processed_at_utc = datetime.now(UTC)
            row.updated_at_utc = row.processed_at_utc
            await session.commit()
            return to_pending_shift(row)

    async def _get_row(self, session, user_id: int, pending_shift_id: int) -> PendingShiftTable:
        row = await session.scalar(
            select(PendingShiftTable).where(
                PendingShiftTable.id == pending_shift_id,
                PendingShiftTable.user_id == user_id,
            )
        )
        if row is None:
            raise LookupError("Ожидающая смена не найдена.")
        return row


def _derive_status(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return PendingShiftStatus.WAITING_ARRIVAL
    if end is None:
        return PendingShiftStatus.WAITING_DEPARTURE
    return PendingShiftStatus.READY if _as_utc(end) > _as_utc(start) else PendingShiftStatus.ATTENTION


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
