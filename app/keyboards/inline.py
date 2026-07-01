from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import WorkSession


def today_keyboard(active: WorkSession | None) -> InlineKeyboardMarkup:
    # клавиатура дня
    builder = InlineKeyboardBuilder()
    if active is None:
        builder.button(text="🟢 Начать работу", callback_data="work:start")
    else:
        active_break = next((item for item in active.breaks if item.ended_at_utc is None), None)
        if active_break:
            builder.button(text="▶️ Продолжить работу", callback_data="work:break_finish")
        else:
            builder.button(text="☕ Начать перерыв", callback_data="work:break_start")
        builder.button(text="🔴 Завершить работу", callback_data="work:finish")
    builder.adjust(1)
    return builder.as_markup()


def calendar_day_keyboard(work_date: str) -> InlineKeyboardMarkup:
    # клавиатура календаря
    builder = InlineKeyboardBuilder()
    builder.button(text="Рабочий день", callback_data=f"calendar:set:{work_date}:workday")
    builder.button(text="Выходной", callback_data=f"calendar:set:{work_date}:weekend")
    builder.button(text="🏖 Отпуск", callback_data=f"calendar:set:{work_date}:vacation")
    builder.button(text="🤒 Больничный", callback_data=f"calendar:set:{work_date}:sick_leave")
    builder.button(text="🕊 Отгул", callback_data=f"calendar:set:{work_date}:day_off")
    builder.button(
        text="Неоплачиваемый",
        callback_data=f"calendar:set:{work_date}:unpaid_leave",
    )
    builder.button(text="📆 Другая дата", callback_data="calendar:date")
    builder.adjust(2, 1)
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    # клавиатура настройки
    builder = InlineKeyboardBuilder()
    entries = [
        ("💵 Зарплата", "settings:salary"),
        ("🎁 Премия", "settings:bonus"),
        ("🎯 Цель", "settings:target"),
        ("🕒 Норма дня", "settings:workday"),
        ("🕘 Начало дня", "settings:work_start_time"),
        ("📈 Правило переработки", "settings:overtime_rule"),
        ("💰 База ставки", "settings:rate_basis"),
        ("🧮 Своя ставка", "settings:custom_rate"),
        ("📉 Недоработка", "settings:underwork"),
        ("📅 Будний коэффициент", "settings:weekday_multiplier"),
        ("🗓 Суббота", "settings:saturday_multiplier"),
        ("☀️ Воскресенье", "settings:sunday_multiplier"),
        ("🎉 Праздник", "settings:holiday_multiplier"),
        ("⌛ Округление", "settings:rounding"),
        ("⏱ Лимит будня", "settings:max_weekday"),
        ("📆 Лимит суббот", "settings:max_saturdays"),
        ("⏳ Часы субботы", "settings:saturday_hours"),
        ("☀️ Работа в воскресенье", "settings:allow_sunday"),
        ("🔔 Напоминания", "settings:reminders"),
        ("⏰ Время прихода", "settings:arrival_time"),
        ("🏁 Норма до ухода", "settings:departure_hours"),
        ("🌙 Контроль смены", "settings:open_shift_time"),
        ("☕ Лимит перерыва", "settings:open_break"),
        ("🌍 Часовой пояс", "settings:timezone"),
    ]
    for text, data in entries:
        builder.button(text=text, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()


def choice_keyboard(prefix: str, values: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for title, value in values:
        builder.button(text=title, callback_data=f"{prefix}:{value}")
    builder.adjust(1)
    return builder.as_markup()


def history_keyboard(session_ids: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session_id in session_ids:
        builder.button(text=f"Смена #{session_id}", callback_data=f"history:view:{session_id}")
    builder.button(text="➕ Добавить вручную", callback_data="history:add")
    builder.button(text="↩️ Восстановить последнюю", callback_data="history:restore")
    builder.adjust(2)
    return builder.as_markup()


def session_keyboard(session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить", callback_data=f"history:edit:{session_id}")
    builder.button(text="🗑 Удалить", callback_data=f"history:delete:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def export_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="CSV за месяц", callback_data="export:csv")
    builder.button(text="JSON-копия", callback_data="export:json")
    builder.adjust(1)
    return builder.as_markup()
