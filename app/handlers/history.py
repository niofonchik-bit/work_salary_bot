from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import (
    cancel_keyboard,
    history_delete_keyboard,
    history_keyboard,
    session_keyboard,
)
from app.keyboards.main import MainButtons
from app.services.reports import build_history_report
from app.states.forms import ManualSessionForm, SessionEditForm

router = Router(name="history")


@router.message(F.text == MainButtons.HISTORY)
async def history_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    await _show_history(message, context, user_id)


@router.callback_query(F.data == "history:list")
async def history_list_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    await state.clear()
    await _show_history(callback, context, user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("history:view:"))
async def history_view_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    shown = await _show_session(callback, context, user_id, session_id)
    if shown:
        await callback.answer()
    else:
        await callback.answer("Смена не найдена.", show_alert=True)


@router.callback_query(F.data == "history:add")
async def history_add_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    await state.set_state(ManualSessionForm.value)
    await context.ui.show(
        callback,
        "<b>➕ Ручная смена</b>\n\nВведите смену в формате:\n<code>01.07.2026 08:00-17:00</code>",
        reply_markup=cancel_keyboard("history:cancel:list"),
    )
    await callback.answer()


@router.message(ManualSessionForm.value)
async def history_add_value_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    user = await context.users.get(user_id)
    try:
        date_part, time_part = (message.text or "").strip().split(maxsplit=1)
        start_text, end_text = time_part.split("-", 1)
        start_local = datetime.strptime(f"{date_part} {start_text}", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(user.timezone)
        )
        end_local = datetime.strptime(f"{date_part} {end_text}", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(user.timezone)
        )
        if end_local <= start_local:
            end_local += timedelta(days=1)
        session = await context.sessions.add_manual(
            user_id,
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
        )
    except (ValueError, TypeError) as error:
        await context.ui.show(
            message,
            "<b>➕ Ручная смена</b>\n\n"
            f"⚠️ Некорректный формат или пересечение смен: {error}\n\n"
            "Введите смену в формате:\n<code>01.07.2026 08:00-17:00</code>",
            reply_markup=cancel_keyboard("history:cancel:list"),
        )
        return
    await context.audit.add(user_id, "work_session", session.id, "manual_add")
    await state.clear()
    await _show_history(message, context, user_id, f"✅ Смена #{session.id} добавлена.")


@router.callback_query(F.data.startswith("history:edit:"))
async def history_edit_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    session = await context.sessions.get(user_id, session_id)
    if session is None:
        await callback.answer("Смена не найдена.", show_alert=True)
        return
    await state.set_state(SessionEditForm.value)
    await state.update_data(session_id=session_id, is_open=session.ended_at_utc is None)
    prompt = (
        "Введите новое время прихода:\n<code>01.07.2026 08:00</code>"
        if session.ended_at_utc is None
        else "Введите новый интервал:\n<code>01.07.2026 08:00-17:00</code>"
    )
    await context.ui.show(
        callback,
        f"<b>✏️ Изменение смены #{session_id}</b>\n\n{prompt}",
        reply_markup=cancel_keyboard(f"history:cancel:view:{session_id}"),
    )
    await callback.answer()


@router.message(SessionEditForm.value)
async def history_edit_value_handler(
    message: Message,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(message, context)
    user = await context.users.get(user_id)
    data = await state.get_data()
    session_id = int(data["session_id"])
    is_open = bool(data["is_open"])
    prompt = (
        "Введите новое время прихода:\n<code>01.07.2026 08:00</code>"
        if is_open
        else "Введите новый интервал:\n<code>01.07.2026 08:00-17:00</code>"
    )
    try:
        if is_open:
            start_local = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M").replace(
                tzinfo=ZoneInfo(user.timezone)
            )
            end_local = None
        else:
            date_part, time_part = (message.text or "").strip().split(maxsplit=1)
            start_text, end_text = time_part.split("-", 1)
            start_local = datetime.strptime(
                f"{date_part} {start_text}",
                "%d.%m.%Y %H:%M",
            ).replace(tzinfo=ZoneInfo(user.timezone))
            end_local = datetime.strptime(
                f"{date_part} {end_text}",
                "%d.%m.%Y %H:%M",
            ).replace(tzinfo=ZoneInfo(user.timezone))
            if end_local <= start_local:
                end_local += timedelta(days=1)
        updated = await context.sessions.update_time(
            user_id,
            session_id,
            start_local.astimezone(UTC),
            end_local.astimezone(UTC) if end_local else None,
        )
    except (ValueError, TypeError) as error:
        await context.ui.show(
            message,
            f"<b>✏️ Изменение смены #{session_id}</b>\n\n⚠️ Некорректное значение: {error}\n\n{prompt}",
            reply_markup=cancel_keyboard(f"history:cancel:view:{session_id}"),
        )
        return
    await context.audit.add(user_id, "work_session", updated.id, "edit")
    await state.clear()
    await _show_session(message, context, user_id, updated.id, f"✅ Смена #{updated.id} обновлена.")


@router.callback_query(F.data.startswith("history:delete_confirm:"))
async def history_delete_confirm_handler(callback: CallbackQuery, context: AppContext) -> None:
    session_id = int(callback.data.rsplit(":", 1)[1])
    await context.ui.show(
        callback,
        f"<b>Удаление смены #{session_id}</b>\n\n"
        "Смена будет скрыта из расчётов. Её можно восстановить из истории.",
        reply_markup=history_delete_keyboard(session_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:delete:"))
async def history_delete_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await context.work_time.delete(user_id, session_id)
        await _show_history(callback, context, user_id, f"✅ Смена #{session_id} удалена.")
        await callback.answer("Смена удалена.")
    except LookupError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(F.data == "history:restore")
async def history_restore_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    try:
        session = await context.work_time.restore_last(user_id)
        await _show_history(callback, context, user_id, f"✅ Смена #{session.id} восстановлена.")
        await callback.answer(f"Смена #{session.id} восстановлена.")
    except (LookupError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(F.data == "history:cancel:list")
async def history_cancel_list_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    await state.clear()
    await _show_history(callback, context, user_id, "Действие отменено.")
    await callback.answer("Действие отменено.")


@router.callback_query(F.data.startswith("history:cancel:view:"))
async def history_cancel_view_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    await state.clear()
    await _show_session(callback, context, user_id, session_id, "Действие отменено.")
    await callback.answer("Действие отменено.")


async def _show_history(
    event: Message | CallbackQuery,
    context: AppContext,
    user_id: int,
    notice: str | None = None,
) -> None:
    bundle = await context.analysis.month(user_id)
    text = build_history_report(bundle.sessions, bundle.user)
    if notice:
        text = f"{notice}\n\n{text}"
    await context.ui.show(
        event,
        text,
        reply_markup=history_keyboard([item.id for item in bundle.sessions[-12:]]),
    )


async def _show_session(
    event: Message | CallbackQuery,
    context: AppContext,
    user_id: int,
    session_id: int,
    notice: str | None = None,
) -> bool:
    session = await context.sessions.get(user_id, session_id)
    if session is None:
        return False
    user = await context.users.get(user_id)
    zone = ZoneInfo(user.timezone)
    start = session.started_at_utc.astimezone(zone)
    end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
    lines = [f"<b>Смена #{session.id}</b>", "", f"Приход: {start:%d.%m.%Y %H:%M}"]
    lines.append(f"Уход: {end:%d.%m.%Y %H:%M}" if end else "Уход: смена открыта")
    lines.append(f"Перерывов: {len(session.breaks)}")
    text = "\n".join(lines)
    if notice:
        text = f"{notice}\n\n{text}"
    await context.ui.show(event, text, reply_markup=session_keyboard(session.id))
    return True
