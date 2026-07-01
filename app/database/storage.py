from __future__ import annotations

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from app.repositories.fsm import FsmRepository


class DatabaseStorage(BaseStorage):
    def __init__(self, repository: FsmRepository):
        self.repository = repository

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        # состояние fsm
        state_value = state.state if isinstance(state, State) else state
        await self.repository.set_state(_serialize_key(key), state_value)

    async def get_state(self, key: StorageKey) -> str | None:
        state, _ = await self.repository.get(_serialize_key(key))
        return state

    async def set_data(self, key: StorageKey, data: dict[str, object]) -> None:
        # содержимое fsm
        await self.repository.set_data(_serialize_key(key), dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, object]:
        _, data = await self.repository.get(_serialize_key(key))
        return data

    async def close(self) -> None:
        return None


def _serialize_key(key: StorageKey) -> str:
    return ":".join(
        str(value)
        for value in (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id or 0,
            key.business_connection_id or "-",
            key.destiny,
        )
    )
