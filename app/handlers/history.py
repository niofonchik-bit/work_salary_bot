from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import history_keyboard, session_keyboard
from app.keyboards.main import MainButtons
from app.services.reports import build_history_report
from app.states.forms import ManualSessionForm, SessionEditForm

router = Router(name="history")


@router.message(F.text == MainButtons.HISTORY)
async def history_handler(message: Message, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    bundle = await context.analysis.month(user_id)
    await message.answer(
        build_history_report(bundle.sessions, bundle.user),
        reply_markup=history_keyboard([item.id for item in bundle.sessions[-12:]]),
    )


@router.callback_query(F.data.startswith("history:view:"))
async def history_view_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    session = await context.sessions.get(user_id, session_id)
    if session is None:
        await callback.answer("Смена не найдена.", show_alert=True)
        return
    user = await context.users.get(user_id)
    zone = ZoneInfo(user.timezone)
    start = session.started_at_utc.astimezone(zone)
    end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
    text = (
        f"<b>Смена #{session.id}</b>\n\nПриход: {start:%d.%m.%Y %H:%M}\nУход: {end:%d.%m.%Y %H:%M}"
        if end
        else f"<b>Смена #{session.id}</b>\n\nСмена открыта"
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=session_keyboard(session.id))
    await callback.answer()


@router.callback_query(F.data == "history:add")
async def history_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManualSessionForm.value)
    await callback.message.answer("Введите смену в формате:\n<code>01.07.2026 08:00-17:00</code>")
    await callback.answer()


@router.message(ManualSessionForm.value)
async def history_add_value_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    user = await context.users.get(user_id)
    try:
        date_part, time_part = message.text.strip().split(maxsplit=1)
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
        await message.answer(f"Некорректный формат или пересечение смен: {error}")
        return
    await context.audit.add(user_id, "work_session", session.id, "manual_add")
    await state.clear()
    await message.answer(f"Смена #{session.id} добавлена.")


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
    await callback.message.answer(prompt)
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
    try:
        if is_open:
            start_local = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M").replace(
                tzinfo=ZoneInfo(user.timezone)
            )
            end_local = None
        else:
            date_part, time_part = message.text.strip().split(maxsplit=1)
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
        await message.answer(f"Некорректное значение: {error}")
        return
    await context.audit.add(user_id, "work_session", updated.id, "edit")
    await state.clear()
    await message.answer(f"Смена #{updated.id} обновлена.")


@router.callback_query(F.data.startswith("history:delete:"))
async def history_delete_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    session_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await context.work_time.delete(user_id, session_id)
        await callback.answer("Смена удалена.")
    except LookupError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(F.data == "history:restore")
async def history_restore_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    try:
        session = await context.work_time.restore_last(user_id)
        await callback.answer(f"Смена #{session.id} восстановлена.", show_alert=True)
    except (LookupError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
