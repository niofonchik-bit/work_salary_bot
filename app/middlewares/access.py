from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Config


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        config: Config = data["config"]
        user = data.get("event_from_user")
        if user is None or not config.allowed_user_ids or user.id in config.allowed_user_ids:
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/myid"):
            return await handler(event, data)

        text = (
            "Доступ к боту закрыт.\n"
            f"Ваш Telegram ID: <code>{user.id}</code>\n"
            "Добавьте его в ALLOWED_USER_IDS в файле .env."
        )
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещён", show_alert=True)
        return None
