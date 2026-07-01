from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import edit_or_answer, ensure_user
from app.keyboards.inline import (
    delete_confirmation_keyboard,
    history_keyboard,
    session_keyboard,
)
from app.keyboards.main import MainButtons
from app.services.report_builder import build_session_detail
from app.states.forms import AddSessionStates, EditSessionStates
from app.utils.formatters import (
    MONTH_NAMES,
    combine_local,
    format_duration,
    month_bounds_utc,
    parse_date,
    parse_time,
)

router = Router(name="history")
PAGE_SIZE = 8


@router.message(F.text == MainButtons.HISTORY)
async def history_menu_handler(message: Message, db: Database, config: Config) -> None:
    user_id, user, now_local = await ensure_user(message, db, config)
    text, markup = await _build_history(db, user_id, user.timezone, now_local.year, now_local.month, 0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "history:current")
async def history_current_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    user_id, user, now_local = await ensure_user(callback, db, config)
    text, markup = await _build_history(db, user_id, user.timezone, now_local.year, now_local.month, 0)
    await edit_or_answer(callback, text, markup)


@router.callback_query(F.data.startswith("history:page:"))
async def history_page_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    _, _, year_raw, month_raw, page_raw = callback.data.split(":")
    year, month, page = int(year_raw), int(month_raw), int(page_raw)
    user_id, user, _ = await ensure_user(callback, db, config)
    text, markup = await _build_history(db, user_id, user.timezone, year, month, page)
    await edit_or_answer(callback, text, markup)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("session:view:"))
async def session_view_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    user_id, user, now_local = await ensure_user(callback, db, config)
    session = await db.get_session(session_id)
    if session is None or session.user_id != user_id:
        await callback.answer("Смена не найдена", show_alert=True)
        return
    await edit_or_answer(
        callback,
        build_session_detail(session, user.timezone, now_local.astimezone(UTC)),
        session_keyboard(session),
    )


@router.callback_query(F.data == "session:add")
async def session_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddSessionStates.date)
    if callback.message:
        await callback.message.answer("Введите дату смены в формате <code>ДД.ММ.ГГГГ</code>:")


@router.message(AddSessionStates.date)
async def add_session_date_handler(message: Message, state: FSMContext) -> None:
    try:
        value = parse_date(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(date=value.isoformat())
    await state.set_state(AddSessionStates.start)
    await message.answer("Введите время прихода в формате <code>ЧЧ:ММ</code>:")


@router.message(AddSessionStates.start)
async def add_session_start_handler(message: Message, state: FSMContext) -> None:
    try:
        value = parse_time(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(start=value.isoformat())
    await state.set_state(AddSessionStates.end)
    await message.answer("Введите время ухода в формате <code>ЧЧ:ММ</code>:")


@router.message(AddSessionStates.end)
async def add_session_end_handler(message: Message, state: FSMContext) -> None:
    try:
        value = parse_time(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(end=value.isoformat())
    await state.set_state(AddSessionStates.break_minutes)
    await message.answer("Введите перерыв в минутах. Если его не было — <code>0</code>:")


@router.message(AddSessionStates.break_minutes)
async def add_session_break_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    try:
        break_minutes = int((message.text or "").strip())
        if break_minutes < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "Введите неотрицательное количество минут, например <code>0</code> или <code>30</code>."
        )
        return

    data = await state.get_data()
    user_id, user, _ = await ensure_user(message, db, config)
    day = datetime.fromisoformat(data["date"]).date()
    start_clock = datetime.fromisoformat(f"2000-01-01T{data['start']}").time()
    end_clock = datetime.fromisoformat(f"2000-01-01T{data['end']}").time()
    start_local = combine_local(day, start_clock, user.timezone)
    end_local = combine_local(day, end_clock, user.timezone)
    if end_local <= start_local:
        end_local += timedelta(days=1)

    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    if break_minutes >= int((end_utc - start_utc).total_seconds() / 60):
        await message.answer("Перерыв не может быть равен или превышать длительность смены.")
        return
    if await db.has_overlap(user_id, start_utc, end_utc):
        await message.answer("Эта смена пересекается с уже сохранённой записью.")
        return

    session = await db.create_session(user_id, start_utc, end_utc, break_minutes)
    await state.clear()
    await message.answer(
        "Смена добавлена ✅\n\n" + build_session_detail(session, user.timezone, datetime.now(UTC)),
        reply_markup=session_keyboard(session),
    )


@router.callback_query(F.data.startswith("session:edit_start:"))
async def edit_start_begin_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    await state.set_state(EditSessionStates.start)
    await state.update_data(session_id=session_id)
    if callback.message:
        await callback.message.answer("Введите новое время прихода в формате <code>ЧЧ:ММ</code>:")


@router.callback_query(F.data.startswith("session:edit_end:"))
async def edit_end_begin_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    await state.set_state(EditSessionStates.end)
    await state.update_data(session_id=session_id)
    if callback.message:
        await callback.message.answer("Введите новое время ухода в формате <code>ЧЧ:ММ</code>:")


@router.callback_query(F.data.startswith("session:edit_break:"))
async def edit_break_begin_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    await state.set_state(EditSessionStates.break_minutes)
    await state.update_data(session_id=session_id)
    if callback.message:
        await callback.message.answer("Введите новый перерыв в минутах:")


@router.message(EditSessionStates.start)
async def edit_start_value_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    try:
        clock = parse_time(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await _update_session_time(message, state, db, config, clock, "start")


@router.message(EditSessionStates.end)
async def edit_end_value_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    try:
        clock = parse_time(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await _update_session_time(message, state, db, config, clock, "end")


@router.message(EditSessionStates.break_minutes)
async def edit_break_value_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    try:
        minutes = int((message.text or "").strip())
        if minutes < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите неотрицательное количество минут.")
        return

    data = await state.get_data()
    user_id, user, _ = await ensure_user(message, db, config)
    session = await db.get_session(int(data["session_id"]))
    if session is None or session.user_id != user_id:
        await state.clear()
        await message.answer("Смена не найдена.")
        return
    if session.ended_at_utc:
        duration = int((session.ended_at_utc - session.started_at_utc).total_seconds() / 60)
        if minutes >= duration:
            await message.answer("Перерыв не может быть равен или превышать длительность смены.")
            return

    updated = await db.update_session(session.id, break_minutes=minutes)
    await state.clear()
    await message.answer(
        "Перерыв обновлён ✅\n\n" + build_session_detail(updated, user.timezone, datetime.now(UTC)),
        reply_markup=session_keyboard(updated),
    )


@router.callback_query(F.data.startswith("session:delete_confirm:"))
async def delete_confirm_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    await edit_or_answer(
        callback,
        "Удалить эту смену? Действие нельзя отменить.",
        delete_confirmation_keyboard(session_id),
    )


@router.callback_query(F.data.startswith("session:delete:"))
async def delete_session_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    session_id = int(callback.data.rsplit(":", 1)[1])
    user_id, _, _ = await ensure_user(callback, db, config)
    session = await db.get_session(session_id)
    if session is None or session.user_id != user_id:
        await callback.answer("Смена не найдена", show_alert=True)
        return
    await db.delete_session(session_id)
    await edit_or_answer(callback, "Смена удалена ✅")


async def _update_session_time(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    clock,
    field: str,
) -> None:
    data = await state.get_data()
    user_id, user, _ = await ensure_user(message, db, config)
    session = await db.get_session(int(data["session_id"]))
    if session is None or session.user_id != user_id:
        await state.clear()
        await message.answer("Смена не найдена.")
        return

    zone = ZoneInfo(user.timezone)
    current_start = session.started_at_utc.astimezone(zone)
    current_end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None

    if field == "start":
        new_start_local = datetime.combine(current_start.date(), clock, tzinfo=zone)
        new_start_utc = new_start_local.astimezone(UTC)
        new_end_utc = session.ended_at_utc
        if new_end_utc and new_start_utc >= new_end_utc:
            await message.answer("Новое время прихода должно быть раньше ухода.")
            return
    else:
        if current_end is None:
            await state.clear()
            await message.answer("У активной смены ещё нет времени ухода.")
            return
        new_end_local = datetime.combine(current_end.date(), clock, tzinfo=zone)
        if new_end_local <= current_start:
            new_end_local += timedelta(days=1)
        new_start_utc = session.started_at_utc
        new_end_utc = new_end_local.astimezone(UTC)

    if await db.has_overlap(user_id, new_start_utc, new_end_utc, exclude_session_id=session.id):
        await message.answer("Новое время пересекается с другой сменой.")
        return

    try:
        if field == "start":
            updated = await db.update_session(session.id, started_at_utc=new_start_utc)
        else:
            updated = await db.update_session(session.id, ended_at_utc=new_end_utc)
    except ValueError:
        await message.answer("После изменения перерыв должен оставаться короче длительности смены.")
        return

    await state.clear()
    await message.answer(
        "Время обновлено ✅\n\n" + build_session_detail(updated, user.timezone, datetime.now(UTC)),
        reply_markup=session_keyboard(updated),
    )


async def _build_history(
    db: Database,
    user_id: int,
    timezone_name: str,
    year: int,
    month: int,
    page: int,
):
    start_utc, end_utc = month_bounds_utc(year, month, timezone_name)
    all_sessions = await db.list_sessions(user_id, start_utc, end_utc)
    total_pages = max(1, math.ceil(len(all_sessions) / PAGE_SIZE))
    page = min(max(0, page), total_pages - 1)
    page_sessions = all_sessions[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    total_minutes = 0
    now_utc = datetime.now(UTC)
    for session in all_sessions:
        end = session.ended_at_utc or now_utc
        total_minutes += max(
            0,
            int(round((end - session.started_at_utc).total_seconds() / 60)) - session.break_minutes,
        )

    text = (
        f"<b>🗓 История: {MONTH_NAMES[month]} {year}</b>\n\n"
        f"Смен: <b>{len(all_sessions)}</b>\n"
        f"Общее время: <b>{format_duration(total_minutes)}</b>"
    )
    if not all_sessions:
        text += "\n\nЗаписей за этот месяц пока нет."

    markup = history_keyboard(
        page_sessions,
        year,
        month,
        page,
        total_pages,
        timezone_name,
    )
    return text, markup
