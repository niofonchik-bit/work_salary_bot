from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import (
    pending_shift_bulk_keyboard,
    pending_shift_keyboard,
    pending_shift_list_keyboard,
    pending_shift_reject_keyboard,
    pending_shift_time_cancel_keyboard,
)
from app.keyboards.main import MainButtons
from app.services.geofence_notifications import render_pending_shift, sync_pending_notification
from app.states.forms import PendingShiftTimeForm

router = Router(name="geofence")


@router.message(F.text == MainButtons.PENDING)
async def pending_list_message_handler(
    message: Message,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    await _show_list(message, context, user_id)


@router.callback_query(F.data == "geofence:list")
async def pending_list_callback_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    await state.clear()
    await _show_list(callback, context, user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("geofence:view:"))
async def pending_view_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    pending_shift_id = int(callback.data.rsplit(":", 1)[1])
    await state.clear()
    try:
        pending = await context.geofence_repository.get(user_id, pending_shift_id)
        user = await context.users.get(user_id)
    except LookupError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await _edit_callback(
        callback,
        render_pending_shift(pending, user.timezone),
        pending_shift_keyboard(pending),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("geofence:confirm:"))
async def pending_confirm_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    pending_shift_id = int(callback.data.rsplit(":", 1)[1])
    try:
        pending, session = await context.geofence.confirm(user_id, pending_shift_id)
        user = await context.users.get(user_id)
        await sync_pending_notification(
            callback.bot,
            context.geofence_repository,
            pending,
            user.timezone,
        )
        await _refresh_secondary_message(callback, pending, user.timezone)
        await callback.answer(f"Смена #{session.id} записана.")
    except (LookupError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(F.data.startswith("geofence:reject_prompt:"))
async def pending_reject_prompt_handler(callback: CallbackQuery, context: AppContext) -> None:
    pending_shift_id = int(callback.data.rsplit(":", 1)[1])
    await _edit_callback(
        callback,
        "<b>Отклонение смены</b>\n\nСобытия геозоны сохранятся в журнале, но рабочая смена создана не будет.",
        pending_shift_reject_keyboard(pending_shift_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("geofence:reject:"))
async def pending_reject_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    pending_shift_id = int(callback.data.rsplit(":", 1)[1])
    try:
        pending = await context.geofence.reject(user_id, pending_shift_id)
        user = await context.users.get(user_id)
        await sync_pending_notification(
            callback.bot,
            context.geofence_repository,
            pending,
            user.timezone,
        )
        await _refresh_secondary_message(callback, pending, user.timezone)
        await callback.answer("Смена отклонена.")
    except (LookupError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(F.data.startswith("geofence:time:"))
async def pending_time_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    _, _, pending_shift_id_text, field = callback.data.split(":", 3)
    pending_shift_id = int(pending_shift_id_text)
    user_id = await ensure_user(callback, context)
    try:
        pending = await context.geofence_repository.get(user_id, pending_shift_id)
    except LookupError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.set_state(PendingShiftTimeForm.value)
    await state.update_data(
        pending_shift_id=pending_shift_id,
        field=field,
        source_chat_id=callback.message.chat.id if isinstance(callback.message, Message) else None,
        source_message_id=callback.message.message_id if isinstance(callback.message, Message) else None,
    )
    title = "прихода" if field == "start" else "ухода"
    await _edit_callback(
        callback,
        f"<b>Изменение времени {title}</b>\n\n"
        f"Дата: <b>{pending.local_date:%d.%m.%Y}</b>\n"
        "Введите время в формате <code>09:00</code>.",
        pending_shift_time_cancel_keyboard(pending_shift_id),
    )
    await callback.answer()


@router.message(PendingShiftTimeForm.value)
async def pending_time_value_handler(
    message: Message,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(message, context)
    data = await state.get_data()
    pending_shift_id = int(data["pending_shift_id"])
    field = str(data["field"])
    try:
        pending = await context.geofence_repository.get(user_id, pending_shift_id)
        user = await context.users.get(user_id)
        parsed_time = datetime.strptime((message.text or "").strip(), "%H:%M").time()
        local_value = datetime.combine(
            pending.local_date,
            parsed_time,
            tzinfo=ZoneInfo(user.timezone),
        )
        if field == "end" and pending.suggested_start_utc is not None:
            start_local = pending.suggested_start_utc.astimezone(ZoneInfo(user.timezone))
            if local_value <= start_local:
                local_value += timedelta(days=1)
        pending = await context.geofence.update_time(
            user_id,
            pending_shift_id,
            field,
            local_value.astimezone(UTC),
        )
    except (LookupError, ValueError) as error:
        await context.ui.delete(message)
        await _edit_source_message(
            message,
            data,
            f"⚠️ {error}\n\nВведите время в формате <code>09:00</code>.",
            pending_shift_time_cancel_keyboard(pending_shift_id),
            pending if "pending" in locals() else None,
        )
        return

    await state.clear()
    await context.ui.delete(message)
    await sync_pending_notification(
        message.bot,
        context.geofence_repository,
        pending,
        user.timezone,
    )
    await _edit_source_message(
        message,
        data,
        render_pending_shift(pending, user.timezone),
        pending_shift_keyboard(pending),
        pending,
    )


@router.callback_query(F.data == "geofence:bulk_prompt")
async def pending_bulk_prompt_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    ready = await context.geofence_repository.list_ready(user_id)
    if not ready:
        await callback.answer("Полных смен для подтверждения нет.", show_alert=True)
        return
    await _edit_callback(
        callback,
        f"<b>Массовое подтверждение</b>\n\nБудет записано смен: <b>{len(ready)}</b>.\n"
        "Смены с недостающим временем останутся в списке.",
        pending_shift_bulk_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "geofence:bulk_confirm")
async def pending_bulk_confirm_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    confirmed, failed = await context.geofence.confirm_all_ready(user_id)
    user = await context.users.get(user_id)
    for pending in confirmed:
        await sync_pending_notification(
            callback.bot,
            context.geofence_repository,
            pending,
            user.timezone,
        )
    notice = f"✅ Подтверждено смен: {len(confirmed)}."
    if failed:
        notice += f"\n⚠️ Не удалось подтвердить: {len(failed)}."
    await _show_list(callback, context, user_id, notice)
    await callback.answer()


async def _show_list(
    event: Message | CallbackQuery,
    context: AppContext,
    user_id: int,
    notice: str | None = None,
) -> None:
    pending = await context.geofence_repository.list_pending(user_id)
    if pending:
        ready_count = sum(
            item.suggested_start_utc is not None and item.suggested_end_utc is not None for item in pending
        )
        text = (
            "<b>📥 Неподтверждённые смены</b>\n\n"
            f"Всего: <b>{len(pending)}</b>\n"
            f"Полных: <b>{ready_count}</b>\n"
            f"Требуют заполнения: <b>{len(pending) - ready_count}</b>\n\n"
            "Выберите дату для проверки."
        )
        markup = pending_shift_list_keyboard(pending)
    else:
        text = "<b>📥 Неподтверждённые смены</b>\n\nВсе события геозоны обработаны."
        markup = None
    if notice:
        text = f"{notice}\n\n{text}"
    await context.ui.show(event, text, reply_markup=markup)


async def _refresh_secondary_message(
    callback: CallbackQuery,
    pending,
    timezone: str,
) -> None:
    if not isinstance(callback.message, Message):
        return
    if (
        pending.telegram_chat_id == callback.message.chat.id
        and pending.telegram_message_id == callback.message.message_id
    ):
        return
    await contextless_edit(
        callback.message,
        render_pending_shift(pending, timezone),
        None,
    )


async def _edit_source_message(
    message: Message,
    data: dict,
    text: str,
    reply_markup,
    pending,
) -> None:
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if source_chat_id is None or source_message_id is None:
        return
    if (
        pending is not None
        and pending.telegram_chat_id == source_chat_id
        and pending.telegram_message_id == source_message_id
        and pending.status not in {"waiting_arrival", "waiting_departure", "ready", "attention"}
    ):
        return
    try:
        await message.bot.edit_message_text(
            chat_id=source_chat_id,
            message_id=source_message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except Exception:
        return


async def _edit_callback(callback: CallbackQuery, text: str, reply_markup) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        return


async def contextless_edit(message: Message, text: str, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        return
