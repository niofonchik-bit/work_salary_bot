from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.database.database import Database
from app.database.models import UserSettings


async def ensure_user(
    event: Message | CallbackQuery,
    db: Database,
    config: Config,
) -> tuple[int, UserSettings, datetime]:
    source_user = event.from_user
    if source_user is None:
        raise RuntimeError("Telegram user is missing")
    await db.ensure_user(source_user.id, config.default_timezone)
    settings = await db.get_user_settings(source_user.id)
    now_local = datetime.now(ZoneInfo(settings.timezone))
    return source_user.id, settings, now_local


async def edit_or_answer(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)
