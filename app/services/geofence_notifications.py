from __future__ import annotations

from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from app.database.enums import PendingShiftStatus
from app.database.models import PendingShift
from app.keyboards.inline import dismiss_keyboard, pending_shift_keyboard
from app.repositories.geofence import GeofenceRepository
from app.utils.formatters import format_minutes


async def sync_pending_notification(
    bot: Bot,
    repository: GeofenceRepository,
    pending: PendingShift,
    timezone: str,
) -> bool:
    # уведомление ожидающей смены
    text = render_pending_shift(pending, timezone)
    markup = (
        dismiss_keyboard()
        if pending.status in {PendingShiftStatus.CONFIRMED, PendingShiftStatus.REJECTED}
        else pending_shift_keyboard(pending)
    )

    if pending.telegram_chat_id is not None and pending.telegram_message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=pending.telegram_chat_id,
                message_id=pending.telegram_message_id,
                text=text,
                reply_markup=markup,
            )
            return True
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).lower():
                return True
        except TelegramAPIError:
            return False

    try:
        message = await bot.send_message(pending.user_id, text, reply_markup=markup)
    except TelegramAPIError:
        return False
    await repository.update_message(
        pending.user_id,
        pending.id,
        message.chat.id,
        message.message_id,
    )
    return True


def render_pending_shift(pending: PendingShift, timezone: str) -> str:
    # текст ожидающей смены
    zone = ZoneInfo(timezone)
    start = pending.suggested_start_utc.astimezone(zone) if pending.suggested_start_utc else None
    end = pending.suggested_end_utc.astimezone(zone) if pending.suggested_end_utc else None

    if pending.status == PendingShiftStatus.CONFIRMED:
        duration = _duration_text(pending)
        return (
            "✅ <b>Смена записана</b>\n\n"
            f"Дата: <b>{pending.local_date:%d.%m.%Y}</b>\n"
            f"Приход: <b>{start:%H:%M}</b>\n"
            f"Уход: <b>{end:%H:%M}</b>\n"
            f"Итого: <b>{duration}</b>"
        )
    if pending.status == PendingShiftStatus.REJECTED:
        return f"❌ <b>Смена отклонена</b>\n\nДата: <b>{pending.local_date:%d.%m.%Y}</b>"

    lines = [
        "🕘 <b>Смена ожидает подтверждения</b>",
        "",
        f"Дата: <b>{pending.local_date:%d.%m.%Y}</b>",
        f"Приход: <b>{start:%H:%M}</b>" if start else "Приход: <b>не найден</b>",
        f"Уход: <b>{end:%H:%M}</b>" if end else "Уход: <b>не найден</b>",
    ]

    if pending.work_session_id is not None and pending.status not in {
        PendingShiftStatus.CONFIRMED,
        PendingShiftStatus.REJECTED,
    }:
        lines.append("Источник прихода: <b>ручная отметка</b>")

    if start and end:
        if end > start:
            lines.append(f"Продолжительность: <b>{_duration_text(pending)}</b>")
        else:
            lines.extend(["", "⚠️ Время ухода не может быть раньше времени прихода."])
    elif start is None and end is not None:
        lines.extend(["", "⚠️ Событие прихода не найдено. Укажите время начала смены."])
    else:
        lines.extend(["", "Смена будет записана только после подтверждения."])
    return "\n".join(lines)


def _duration_text(pending: PendingShift) -> str:
    if pending.suggested_start_utc is None or pending.suggested_end_utc is None:
        return "—"
    start = pending.suggested_start_utc.astimezone(UTC)
    end = pending.suggested_end_utc.astimezone(UTC)
    return format_minutes(max(0, int((end - start).total_seconds() // 60)))
