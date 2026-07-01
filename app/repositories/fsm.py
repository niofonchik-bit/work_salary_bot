from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete

from app.database.session import Database
from app.database.tables import FsmStateTable

_MISSING = object()


class FsmRepository:
    def __init__(self, database: Database):
        self.database = database

    async def get(self, key: str) -> tuple[str | None, dict]:
        async with self.database.sessions()() as session:
            row = await session.get(FsmStateTable, key)
            return (row.state, dict(row.data or {})) if row else (None, {})

    async def set_state(self, key: str, state: str | None) -> None:
        await self._upsert(key, state=state)

    async def set_data(self, key: str, data: dict) -> None:
        await self._upsert(key, data=data)

    async def clear(self, key: str) -> None:
        async with self.database.sessions()() as session:
            await session.execute(delete(FsmStateTable).where(FsmStateTable.storage_key == key))
            await session.commit()

    async def _upsert(
        self,
        key: str,
        state: str | None | object = _MISSING,
        data: dict | object = _MISSING,
    ) -> None:
        # состояние диалога
        async with self.database.sessions()() as session:
            row = await session.get(FsmStateTable, key)
            if row is None:
                row = FsmStateTable(
                    storage_key=key,
                    state=None if state is _MISSING else state,
                    data={} if data is _MISSING else data,
                    updated_at_utc=datetime.now(UTC),
                )
                session.add(row)
            else:
                if state is not _MISSING:
                    row.state = state
                if data is not _MISSING:
                    row.data = data
                row.updated_at_utc = datetime.now(UTC)
            await session.commit()
