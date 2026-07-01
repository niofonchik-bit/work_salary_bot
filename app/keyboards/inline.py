from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import UserSettings, WorkSession
from app.utils.formatters import add_months


def analytics_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сегодня", callback_data="analytics:today")
    builder.button(text="Неделя", callback_data="analytics:week")
    builder.button(text="Месяц", callback_data="analytics:month")
    builder.adjust(3)
    return builder.as_markup()


def goal_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value in (70_000, 80_000, 90_000):
        builder.button(text=f"{value // 1000} 000 ₽", callback_data=f"goal:set:{value}")
    builder.button(text="Ввести вручную", callback_data="goal:custom")
    builder.adjust(3, 1)
    return builder.as_markup()


def settings_keyboard(user: UserSettings) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Зарплата", callback_data="settings:salary")
    builder.button(text="🎁 Премия", callback_data="settings:bonus")
    builder.button(text="🎯 Цель", callback_data="settings:target")
    builder.button(text="🕒 Норма дня", callback_data="settings:workday")
    builder.button(text="📅 Норма месяца", callback_data="settings:standard")
    builder.button(text="📈 Ставка переработки", callback_data="settings:overtime")
    builder.button(text="🗓 Коэффициент выходных", callback_data="settings:weekend")
    builder.button(text="🌍 Часовой пояс", callback_data="settings:timezone")
    builder.adjust(2)
    return builder.as_markup()


def overtime_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Из зарплаты + премии", callback_data="overtime:total")
    builder.button(text="Только из зарплаты", callback_data="overtime:salary")
    builder.button(text="Своя ставка", callback_data="overtime:custom")
    builder.button(text="Назад", callback_data="settings:open")
    builder.adjust(1)
    return builder.as_markup()


def weekend_multiplier_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value in (1, 1.5, 2):
        builder.button(text=f"×{value:g}", callback_data=f"weekend:{value}")
    builder.button(text="Назад", callback_data="settings:open")
    builder.adjust(3, 1)
    return builder.as_markup()


def history_keyboard(
    sessions: list[WorkSession],
    year: int,
    month: int,
    page: int,
    total_pages: int,
    timezone_name: str,
) -> InlineKeyboardMarkup:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone_name)
    builder = InlineKeyboardBuilder()
    for session in sessions:
        start = session.started_at_utc.astimezone(zone)
        end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
        end_text = end.strftime("%H:%M") if end else "…"
        builder.button(
            text=f"{start:%d.%m}  {start:%H:%M}–{end_text}",
            callback_data=f"session:view:{session.id}",
        )

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"history:page:{year}:{month}:{page - 1}",
            )
        )
    navigation.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"history:page:{year}:{month}:{page + 1}",
            )
        )
    if navigation:
        builder.row(*navigation)

    previous_year, previous_month = add_months(year, month, -1)
    next_year, next_month = add_months(year, month, 1)
    builder.row(
        InlineKeyboardButton(
            text="← Пред. месяц",
            callback_data=f"history:page:{previous_year}:{previous_month}:0",
        ),
        InlineKeyboardButton(
            text="След. месяц →",
            callback_data=f"history:page:{next_year}:{next_month}:0",
        ),
    )
    builder.row(InlineKeyboardButton(text="➕ Добавить смену", callback_data="session:add"))
    return builder.as_markup()


def session_keyboard(session: WorkSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Изменить приход", callback_data=f"session:edit_start:{session.id}")
    if session.ended_at_utc:
        builder.button(text="Изменить уход", callback_data=f"session:edit_end:{session.id}")
    builder.button(text="Изменить перерыв", callback_data=f"session:edit_break:{session.id}")
    builder.button(text="Удалить", callback_data=f"session:delete_confirm:{session.id}")
    builder.button(text="Назад к истории", callback_data="history:current")
    builder.adjust(1)
    return builder.as_markup()


def delete_confirmation_keyboard(session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"session:delete:{session_id}")
    builder.button(text="Отмена", callback_data=f"session:view:{session_id}")
    builder.adjust(2)
    return builder.as_markup()
