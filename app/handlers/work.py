from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user, utc_now
from app.keyboards.inline import today_keyboard
from app.keyboards.main import MainButtons
from app.services.reports import build_today_report
from app.services.time_tracking import session_work_minutes
from app.utils.formatters import format_minutes

router = Router(name="work")


async def show_today(
    event: Message | CallbackQuery,
    context: AppContext,
    notice: str | None = None,
) -> None:
    user_id = await ensure_user(event, context)
    user, day, sessions, now_local = await context.analysis.today(user_id)
    active = next((item for item in sessions if item.ended_at_utc is None), None)
    text = build_today_report(user, day, sessions, now_local)
    if notice:
        text = f"{notice}\n\n{text}"
    await context.ui.show(event, text, reply_markup=today_keyboard(active))


@router.message(F.text == MainButtons.TODAY)
async def today_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    await state.clear()
    await show_today(message, context)


@router.message(F.text == MainButtons.ARRIVE)
async def arrive_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    try:
        session = await context.work_time.start(user_id, utc_now())
    except ValueError as error:
        await show_today(message, context, f"⚠️ {error}")
        return
    user = await context.users.get(user_id)
    local_start = session.started_at_utc.astimezone(ZoneInfo(user.timezone))
    await show_today(message, context, f"✅ Приход зафиксирован: <b>{local_start:%H:%M}</b>")


@router.message(F.text == MainButtons.LEAVE)
async def leave_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    try:
        session = await context.work_time.finish(user_id, utc_now())
    except (LookupError, ValueError) as error:
        await show_today(message, context, f"⚠️ {error}")
        return
    await show_today(
        message,
        context,
        f"✅ Уход зафиксирован. Отработано: <b>{format_minutes(session_work_minutes(session))}</b>",
    )


@router.message(F.text == MainButtons.BREAK)
async def break_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    active = await context.sessions.get_active(user_id)
    if active is None:
        await show_today(message, context, "⚠️ Открытая смена не найдена.")
        return
    active_break = next((item for item in active.breaks if item.ended_at_utc is None), None)
    try:
        if active_break:
            await context.work_time.finish_break(user_id, utc_now())
            notice = "✅ Перерыв завершён."
        else:
            await context.work_time.start_break(user_id, utc_now())
            notice = "✅ Перерыв начат."
    except (LookupError, ValueError) as error:
        notice = f"⚠️ {error}"
    await show_today(message, context, notice)


@router.callback_query(F.data.startswith("work:"))
async def work_callback(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    action = callback.data.split(":", 1)[1]
    try:
        if action == "start":
            await context.work_time.start(user_id, utc_now())
            text = "✅ Приход зафиксирован."
        elif action == "finish":
            await context.work_time.finish(user_id, utc_now())
            text = "✅ Уход зафиксирован."
        elif action == "break_start":
            await context.work_time.start_break(user_id, utc_now())
            text = "✅ Перерыв начат."
        else:
            await context.work_time.finish_break(user_id, utc_now())
            text = "✅ Перерыв завершён."
        await callback.answer(text.replace("✅ ", ""))
    except (LookupError, ValueError) as error:
        text = f"⚠️ {error}"
        await callback.answer(str(error), show_alert=True)
    await show_today(callback, context, text)
