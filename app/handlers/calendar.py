from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.database.enums import DayType
from app.handlers.helpers import ensure_user
from app.keyboards.inline import calendar_day_keyboard
from app.keyboards.main import MainButtons
from app.states.forms import CalendarDateForm
from app.utils.formatters import DAY_TYPE_NAMES, format_minutes

router = Router(name="calendar")


@router.message(F.text == MainButtons.CALENDAR)
async def calendar_handler(message: Message, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    _, day, _, now_local = await context.analysis.today(user_id)
    await message.answer(
        _calendar_text(day.work_date, day.day_type, day.expected_minutes, day.is_paid),
        reply_markup=calendar_day_keyboard(now_local.date().isoformat()),
    )


@router.callback_query(F.data == "calendar:date")
async def calendar_date_handler(callback: CallbackQuery, state: FSMContext) -> None:
    # выбор даты
    await state.set_state(CalendarDateForm.value)
    await callback.message.answer("Введите дату в формате <code>ДД.ММ.ГГГГ</code>:")
    await callback.answer()


@router.message(CalendarDateForm.value)
async def calendar_date_value_handler(
    message: Message,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(message, context)
    user = await context.users.get(user_id)
    try:
        work_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Пример: <code>15.07.2026</code>")
        return
    await context.calendar.ensure_month(
        user_id,
        work_date.year,
        work_date.month,
        user.workday_minutes,
    )
    day = await context.calendar.get_day(user_id, work_date)
    if day is None:
        await message.answer("День календаря не найден.")
        return
    await state.clear()
    await message.answer(
        _calendar_text(day.work_date, day.day_type, day.expected_minutes, day.is_paid),
        reply_markup=calendar_day_keyboard(work_date.isoformat()),
    )


@router.callback_query(F.data.startswith("calendar:set:"))
async def calendar_set_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    _, _, raw_date, day_type = callback.data.split(":", 3)
    work_date = date.fromisoformat(raw_date)
    user = await context.users.get(user_id)
    await context.calendar.ensure_month(
        user_id,
        work_date.year,
        work_date.month,
        user.workday_minutes,
    )
    expected = (
        user.workday_minutes
        if day_type
        in {
            DayType.WORKDAY,
            DayType.VACATION,
            DayType.SICK_LEAVE,
            DayType.DAY_OFF,
            DayType.UNPAID_LEAVE,
        }
        else 0
    )
    is_paid = day_type in {
        DayType.WORKDAY,
        DayType.VACATION,
        DayType.SICK_LEAVE,
        DayType.DAY_OFF,
    }
    await context.calendar.set_day(
        user_id,
        work_date,
        day_type,
        expected,
        is_paid,
    )
    await callback.answer("Календарь обновлён.")
    if callback.message:
        await callback.message.edit_text(
            _calendar_text(work_date, day_type, expected, is_paid),
            reply_markup=calendar_day_keyboard(work_date.isoformat()),
        )


def _calendar_text(work_date: date, day_type: str, expected: int, is_paid: bool) -> str:
    return (
        f"<b>📅 {work_date:%d.%m.%Y}</b>\n\n"
        f"Тип: {DAY_TYPE_NAMES.get(day_type, day_type)}\n"
        f"Норма: {format_minutes(expected)}\n"
        f"Оплата отсутствия: {'да' if is_paid else 'нет'}\n\n"
        "Выберите тип дня:"
    )
