from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import WorkSession

SETTINGS_SECTIONS: dict[str, list[tuple[str, str]]] = {
    "income": [
        ("💵 Зарплата", "salary"),
        ("🎁 Премия", "bonus"),
        ("🎯 Цель месяца", "target"),
    ],
    "schedule": [
        ("🕒 Норма дня", "workday"),
        ("🕘 Начало дня", "work_start_time"),
        ("🌍 Часовой пояс", "timezone"),
    ],
    "payment": [
        ("📈 Правило переработки", "overtime_rule"),
        ("💰 База ставки", "rate_basis"),
        ("🧮 Своя ставка", "custom_rate"),
        ("📉 Недоработка", "underwork"),
        ("⌛ Округление", "rounding"),
    ],
    "multipliers": [
        ("📅 Будний день", "weekday_multiplier"),
        ("🗓 Суббота", "saturday_multiplier"),
        ("☀️ Воскресенье", "sunday_multiplier"),
        ("🎉 Праздник", "holiday_multiplier"),
    ],
    "goal": [
        ("⏱ Лимит будня", "max_weekday"),
        ("📆 Лимит суббот", "max_saturdays"),
        ("⏳ Часы субботы", "saturday_hours"),
        ("☀️ Работа в воскресенье", "allow_sunday"),
    ],
    "reminders": [
        ("🔔 Состояние", "reminders"),
        ("⏰ Время прихода", "arrival_time"),
        ("🏁 Норма до ухода", "departure_hours"),
        ("🌙 Контроль смены", "open_shift_time"),
        ("☕ Лимит перерыва", "open_break"),
    ],
}


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
    builder.button(text="Неоплачиваемый", callback_data=f"calendar:set:{work_date}:unpaid_leave")
    builder.button(text="📆 Другая дата", callback_data="calendar:date")
    builder.adjust(2, 1)
    return builder.as_markup()


def settings_root_keyboard() -> InlineKeyboardMarkup:
    # клавиатура настройки
    builder = InlineKeyboardBuilder()
    entries = [
        ("💵 Доход и цель", "income"),
        ("🕘 Рабочий график", "schedule"),
        ("📈 Расчёт оплаты", "payment"),
        ("📅 Коэффициенты", "multipliers"),
        ("🎯 План цели", "goal"),
        ("🔔 Напоминания", "reminders"),
        ("📍 Автоматизация", "automation"),
    ]
    for text, section in entries:
        builder.button(text=text, callback_data=f"settings:section:{section}")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def settings_section_keyboard(section: str) -> InlineKeyboardMarkup:
    # клавиатура раздела
    builder = InlineKeyboardBuilder()
    for text, field in SETTINGS_SECTIONS.get(section, []):
        builder.button(text=text, callback_data=f"settings:field:{field}")
    builder.button(text="↩️ Все настройки", callback_data="settings:root")
    builder.adjust(1)
    return builder.as_markup()


def choice_keyboard(
    prefix: str,
    values: list[tuple[str, str]],
    back_callback: str,
) -> InlineKeyboardMarkup:
    # клавиатура выбора
    builder = InlineKeyboardBuilder()
    for title, value in values:
        builder.button(text=title, callback_data=f"{prefix}:{value}")
    builder.button(text="✖️ Отмена", callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    # клавиатура отмены
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data=callback_data)
    return builder.as_markup()


def dismiss_keyboard() -> InlineKeyboardMarkup:
    # клавиатура закрытия
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить сообщение", callback_data="ui:dismiss")
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
    builder.button(text="🗑 Удалить", callback_data=f"history:delete_confirm:{session_id}")
    builder.button(text="↩️ К истории", callback_data="history:list")
    builder.adjust(1)
    return builder.as_markup()


def history_delete_keyboard(session_id: int) -> InlineKeyboardMarkup:
    # клавиатура удаления
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data=f"history:delete:{session_id}")
    builder.button(text="✖️ Отмена", callback_data=f"history:view:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def export_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="CSV за месяц", callback_data="export:csv")
    builder.button(text="JSON-копия", callback_data="export:json")
    builder.adjust(1)
    return builder.as_markup()
