from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import ensure_user
from app.keyboards.main import MainButtons
from app.utils.formatters import format_duration

router = Router(name="work_time")


@router.message(F.text == MainButtons.ARRIVE)
async def arrive_handler(message: Message, db: Database, config: Config) -> None:
    user_id, settings, now_local = await ensure_user(message, db, config)
    active = await db.get_active_session(user_id)
    if active:
        started = active.started_at_utc.astimezone(ZoneInfo(settings.timezone))
        await message.answer(f"Рабочий день уже начат.\nПриход: <b>{started:%d.%m.%Y в %H:%M}</b>")
        return

    try:
        await db.start_session(user_id, now_local.astimezone(UTC))
    except ValueError:
        await message.answer("Рабочий день уже начат.")
        return

    await message.answer(f"🟢 Приход зафиксирован: <b>{now_local:%H:%M}</b>")


@router.message(F.text == MainButtons.LEAVE)
async def leave_handler(message: Message, db: Database, config: Config) -> None:
    user_id, settings, now_local = await ensure_user(message, db, config)
    active = await db.get_active_session(user_id)
    if active is None:
        await message.answer("Нет активной смены. Сначала нажмите «🟢 Пришёл».")
        return

    ended_at_utc = now_local.astimezone(UTC)
    if ended_at_utc <= active.started_at_utc:
        await message.answer("Время ухода не может быть раньше времени прихода.")
        return

    try:
        session = await db.end_session(active.id, ended_at_utc)
    except ValueError:
        await message.answer(
            "Не удалось закрыть смену: сохранённый перерыв равен или превышает "
            "длительность смены. Измените перерыв в истории."
        )
        return

    duration = int(round((session.ended_at_utc - session.started_at_utc).total_seconds() / 60))
    duration = max(0, duration - session.break_minutes)
    await message.answer(
        f"🔴 Уход зафиксирован: <b>{now_local:%H:%M}</b>\nОтработано: <b>{format_duration(duration)}</b>"
    )
