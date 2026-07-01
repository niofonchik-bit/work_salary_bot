from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: frozenset[int]):
        self.allowed_user_ids = allowed_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # проверка доступа
        user = data.get("event_from_user")
        if user is None or not self.allowed_user_ids or user.id in self.allowed_user_ids:
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer("Доступ к боту закрыт.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ закрыт.", show_alert=True)
        return None
