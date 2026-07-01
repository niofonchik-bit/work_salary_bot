from __future__ import annotations

from datetime import date, datetime

from app.database.models import GeofenceRegistration, PendingShift, WorkSession
from app.repositories.audit import AuditRepository
from app.repositories.geofence import GeofenceRepository
from app.use_cases.work_time import WorkTimeUseCase


class GeofenceUseCase:
    def __init__(
        self,
        repository: GeofenceRepository,
        work_time: WorkTimeUseCase,
        audit: AuditRepository,
    ):
        self.repository = repository
        self.work_time = work_time
        self.audit = audit

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
        # событие геозоны
        result = await self.repository.register_event(
            user_id,
            local_date,
            zone,
            event_type,
            occurred_at_utc,
            client,
            dedup_minutes,
        )
        await self.audit.add(
            user_id,
            "geofence_event",
            result.event.id,
            "register",
            after_data={
                "event_type": result.event.event_type,
                "occurred_at_utc": result.event.occurred_at_utc.isoformat(),
                "status": result.event.status,
                "pending_shift_id": result.pending_shift.id,
            },
        )
        return result

    async def confirm(self, user_id: int, pending_shift_id: int) -> tuple[PendingShift, WorkSession]:
        # подтверждение смены
        pending = await self.repository.get(user_id, pending_shift_id)
        if pending.work_session_id is not None:
            raise ValueError("Смена уже подтверждена.")
        if pending.suggested_start_utc is None or pending.suggested_end_utc is None:
            raise ValueError("Для подтверждения нужны время прихода и ухода.")
        if pending.suggested_end_utc <= pending.suggested_start_utc:
            raise ValueError("Время ухода должно быть позже времени прихода.")

        session = await self.work_time.add_completed(
            user_id,
            pending.suggested_start_utc,
            pending.suggested_end_utc,
            source="geofence",
        )
        updated = await self.repository.mark_confirmed(user_id, pending_shift_id, session.id)
        await self.audit.add(
            user_id,
            "pending_shift",
            pending_shift_id,
            "confirm",
            after_data={"work_session_id": session.id},
        )
        return updated, session

    async def reject(self, user_id: int, pending_shift_id: int) -> PendingShift:
        # отклонение смены
        pending = await self.repository.mark_rejected(user_id, pending_shift_id)
        await self.audit.add(user_id, "pending_shift", pending_shift_id, "reject")
        return pending

    async def update_time(
        self,
        user_id: int,
        pending_shift_id: int,
        field: str,
        value_utc: datetime,
    ) -> PendingShift:
        # время смены
        pending = await self.repository.update_time(user_id, pending_shift_id, field, value_utc)
        await self.audit.add(
            user_id,
            "pending_shift",
            pending_shift_id,
            "update_time",
            after_data={"field": field, "value_utc": value_utc.isoformat()},
        )
        return pending

    async def confirm_all_ready(
        self,
        user_id: int,
    ) -> tuple[list[PendingShift], list[tuple[PendingShift, str]]]:
        # массовое подтверждение
        confirmed: list[PendingShift] = []
        failed: list[tuple[PendingShift, str]] = []
        for pending in await self.repository.list_ready(user_id):
            try:
                updated, _ = await self.confirm(user_id, pending.id)
                confirmed.append(updated)
            except (LookupError, ValueError) as error:
                failed.append((pending, str(error)))
        return confirmed, failed
