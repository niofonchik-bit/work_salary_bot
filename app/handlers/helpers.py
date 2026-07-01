from __future__ import annotations

from datetime import UTC, datetime

from aiogram.types import CallbackQuery, Message

from app.context import AppContext


async def ensure_user(event: Message | CallbackQuery, context: AppContext) -> int:
    # инициализация пользователя
    user = event.from_user
    if user is None:
        raise RuntimeError("Telegram-пользователь не найден.")
    await context.users.ensure(user.id, context.config.default_timezone)
    return user.id


def utc_now() -> datetime:
    return datetime.now(UTC)
