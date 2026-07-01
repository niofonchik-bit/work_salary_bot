from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import (
    SETTINGS_SECTIONS,
    cancel_keyboard,
    choice_keyboard,
    settings_root_keyboard,
    settings_section_keyboard,
)
from app.keyboards.main import MainButtons
from app.states.forms import SettingForm
from app.utils.formatters import format_minutes, format_money

router = Router(name="settings")

SECTION_TITLES = {
    "income": "💵 Доход и цель",
    "schedule": "🕘 Рабочий график",
    "payment": "📈 Расчёт оплаты",
    "multipliers": "📅 Коэффициенты",
    "goal": "🎯 План достижения цели",
    "reminders": "🔔 Напоминания",
    "automation": "📍 Автоматизация",
}

FIELD_SECTIONS = {field: section for section, entries in SETTINGS_SECTIONS.items() for _, field in entries}

CHOICE_FIELDS = {
    "overtime_rule": (
        "Выберите правило переработки:",
        [
            ("По каждому дню", "daily"),
            ("После нормы месяца", "monthly"),
            ("По балансу на сегодня", "balance"),
        ],
    ),
    "rate_basis": (
        "Выберите базу часовой ставки:",
        [
            ("Зарплата + премия", "total"),
            ("Только зарплата", "salary"),
            ("Своя ставка", "custom"),
        ],
    ),
    "underwork": (
        "Как учитывать недоработку:",
        [("Не уменьшать прогноз", "ignore"), ("Уменьшать прогноз", "deduct")],
    ),
    "reminders": (
        "Состояние напоминаний:",
        [("Включить", "on"), ("Выключить", "off")],
    ),
    "allow_sunday": (
        "Работа по воскресеньям:",
        [("Разрешить", "on"), ("Запретить", "off")],
    ),
    "rounding": (
        "Шаг округления рабочего времени:",
        [(f"{value} мин", str(value)) for value in (1, 5, 10, 15, 30)],
    ),
}

INPUT_PROMPTS = {
    "salary": "Введите чистую зарплату в рублях:",
    "bonus": "Введите чистую премию в рублях:",
    "target": "Введите цель месяца в рублях:",
    "workday": "Введите норму рабочего дня в часах, например 8 или 7.5:",
    "work_start_time": "Введите плановое начало рабочего дня в формате ЧЧ:ММ:",
    "custom_rate": "Введите чистую часовую ставку в рублях:",
    "weekday_multiplier": "Введите коэффициент будней, например 1 или 1.5:",
    "saturday_multiplier": "Введите коэффициент субботы, например 1, 1.5 или 2:",
    "sunday_multiplier": "Введите коэффициент воскресенья:",
    "holiday_multiplier": "Введите коэффициент праздника:",
    "max_weekday": "Введите максимум переработки в будний день в минутах:",
    "max_saturdays": "Введите максимум рабочих суббот в месяц:",
    "saturday_hours": "Введите продолжительность рабочей субботы в часах:",
    "arrival_time": "Введите время напоминания о приходе в формате ЧЧ:ММ:",
    "departure_hours": "Введите норму до напоминания об уходе в часах:",
    "open_shift_time": "Введите время контроля незакрытой смены в формате ЧЧ:ММ:",
    "open_break": "Введите лимит открытого перерыва в минутах:",
    "timezone": "Введите часовой пояс IANA, например Europe/Istanbul:",
}


@router.message(F.text == MainButtons.SETTINGS)
async def settings_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    await context.ui.show(
        message,
        await _settings_root_text(context, user_id),
        reply_markup=settings_root_keyboard(),
    )


@router.callback_query(F.data == "settings:root")
async def settings_root_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    await state.clear()
    await context.ui.show(
        callback,
        await _settings_root_text(context, user_id),
        reply_markup=settings_root_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:section:"))
async def settings_section_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    section = callback.data.rsplit(":", 1)[1]
    if section not in SECTION_TITLES:
        await callback.answer("Раздел не найден.", show_alert=True)
        return
    await _show_section(callback, context, user_id, section)
    await callback.answer()


@router.callback_query(F.data.startswith("settings:field:"))
async def settings_field_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    await ensure_user(callback, context)
    field = callback.data.rsplit(":", 1)[1]
    section = FIELD_SECTIONS.get(field)
    if section is None:
        await callback.answer("Настройка не найдена.", show_alert=True)
        return

    choice = CHOICE_FIELDS.get(field)
    if choice is not None:
        title, values = choice
        await context.ui.show(
            callback,
            f"<b>{SECTION_TITLES[section]}</b>\n\n{title}",
            reply_markup=choice_keyboard(
                f"settings_set:{field}",
                values,
                f"settings:section:{section}",
            ),
        )
        await callback.answer()
        return

    prompt = INPUT_PROMPTS.get(field)
    if prompt is None:
        await callback.answer("Настройка недоступна.", show_alert=True)
        return
    await state.set_state(SettingForm.value)
    await state.update_data(setting=field, section=section)
    await context.ui.show(
        callback,
        f"<b>{SECTION_TITLES[section]}</b>\n\n{prompt}",
        reply_markup=cancel_keyboard(f"settings:cancel:{section}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_set:"))
async def settings_choice_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    _, field, value = callback.data.split(":", 2)
    section = FIELD_SECTIONS.get(field, "payment")
    if field == "reminders":
        await context.users.update_reminder_settings(user_id, "enabled", value == "on")
    elif field == "allow_sunday":
        await context.users.update(user_id, "allow_sunday", value == "on")
    elif field == "rounding":
        await context.users.update_pay_profile(user_id, "rounding_minutes", int(value))
    elif field == "underwork":
        await context.users.update_pay_profile(user_id, "underwork_mode", value)
    else:
        await context.users.update_pay_profile(user_id, field, value)
    await _show_section(callback, context, user_id, section, "✅ Настройка сохранена.")
    await callback.answer("Настройка сохранена.")


@router.callback_query(F.data.startswith("settings:cancel:"))
async def settings_cancel_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    user_id = await ensure_user(callback, context)
    section = callback.data.rsplit(":", 1)[1]
    await state.clear()
    await _show_section(callback, context, user_id, section, "Действие отменено.")
    await callback.answer("Действие отменено.")


@router.message(SettingForm.value)
async def settings_value_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    data = await state.get_data()
    field = str(data.get("setting"))
    section = str(data.get("section") or FIELD_SECTIONS.get(field, "income"))
    raw = (message.text or "").strip()
    try:
        await _save_value(context, user_id, field, raw)
    except (ValueError, ZoneInfoNotFoundError) as error:
        prompt = INPUT_PROMPTS.get(field, "Введите значение:")
        await context.ui.show(
            message,
            f"<b>{SECTION_TITLES[section]}</b>\n\n⚠️ Некорректное значение: {error}\n\n{prompt}",
            reply_markup=cancel_keyboard(f"settings:cancel:{section}"),
        )
        return
    await state.clear()
    await _show_section(message, context, user_id, section, "✅ Настройка сохранена.")


async def _show_section(
    event: Message | CallbackQuery,
    context: AppContext,
    user_id: int,
    section: str,
    notice: str | None = None,
) -> None:
    text = await _settings_section_text(context, user_id, section)
    if notice:
        text = f"{notice}\n\n{text}"
    await context.ui.show(event, text, reply_markup=settings_section_keyboard(section))


async def _save_value(context: AppContext, user_id: int, field: str, raw: str) -> None:
    # сохранение настройки
    normalized = raw.replace(" ", "").replace(",", ".")
    if field in {"salary", "bonus"}:
        cents = _positive_money(normalized)
        db_field = "salary_cents" if field == "salary" else "bonus_cents"
        await context.users.update_pay_profile(user_id, db_field, cents)
        profile = await context.users.get_pay_profile(user_id)
        await context.payments.sync_default_amounts(user_id, profile.salary_cents, profile.bonus_cents)
    elif field == "target":
        cents = _positive_money(normalized)
        bundle = await context.analysis.month(user_id)
        await context.users.update_month(
            user_id,
            bundle.analysis.year,
            bundle.analysis.month,
            "target_cents",
            cents,
        )
    elif field == "workday":
        minutes = _positive_hours(normalized)
        await context.users.update(user_id, "workday_minutes", minutes)
        await context.users.update_reminder_settings(user_id, "departure_after_minutes", minutes)
    elif field == "work_start_time":
        await context.users.update(
            user_id,
            "work_start_time",
            datetime.strptime(raw, "%H:%M").time(),
        )
    elif field == "custom_rate":
        await context.users.update_pay_profile(user_id, "custom_rate_cents", _positive_money(normalized))
    elif field.endswith("_multiplier"):
        percent = round(float(normalized) * 100)
        if percent <= 0:
            raise ValueError("коэффициент должен быть положительным")
        await context.users.update_pay_profile(user_id, f"{field}_percent", percent)
    elif field == "max_weekday":
        await context.users.update(
            user_id,
            "max_weekday_overtime_minutes",
            _non_negative_int(normalized),
        )
    elif field == "max_saturdays":
        await context.users.update(user_id, "max_saturdays", _non_negative_int(normalized))
    elif field == "saturday_hours":
        await context.users.update(user_id, "saturday_minutes", _positive_hours(normalized))
    elif field in {"arrival_time", "open_shift_time"}:
        value = datetime.strptime(raw, "%H:%M").time()
        db_field = "arrival_time" if field == "arrival_time" else "open_shift_time"
        await context.users.update_reminder_settings(user_id, db_field, value)
    elif field == "departure_hours":
        await context.users.update_reminder_settings(
            user_id,
            "departure_after_minutes",
            _positive_hours(normalized),
        )
    elif field == "open_break":
        value = int(normalized)
        if value <= 0:
            raise ValueError("лимит должен быть положительным")
        await context.users.update_reminder_settings(user_id, "open_break_minutes", value)
    elif field == "timezone":
        ZoneInfo(raw)
        await context.users.update(user_id, "timezone", raw)
    else:
        raise ValueError("неизвестная настройка")


async def _settings_root_text(context: AppContext, user_id: int) -> str:
    profile = await context.users.get_pay_profile(user_id)
    month = await context.analysis.month(user_id)
    user = await context.users.get(user_id)
    reminder = await context.users.get_reminder_settings(user_id)
    return "\n".join(
        [
            "<b>⚙️ Настройки</b>",
            "",
            "Параметры сгруппированы по разделам, чтобы меню оставалось компактным.",
            "",
            f"Доход: {format_money(profile.salary_cents + profile.bonus_cents)}",
            f"Цель: {format_money(month.month_settings.target_cents)}",
            f"График: {format_minutes(user.workday_minutes)} с {user.work_start_time:%H:%M}",
            f"Напоминания: {'включены' if reminder.enabled else 'выключены'}",
            f"Геозона: {'включена' if context.config.geofence_enabled else 'выключена'}",
            "",
            "Выберите раздел:",
        ]
    )


async def _settings_section_text(context: AppContext, user_id: int, section: str) -> str:
    user = await context.users.get(user_id)
    profile = await context.users.get_pay_profile(user_id)
    month = await context.analysis.month(user_id)
    reminder = await context.users.get_reminder_settings(user_id)
    title = SECTION_TITLES[section]

    lines = [f"<b>{title}</b>", ""]
    if section == "income":
        lines.extend(
            [
                f"Зарплата: {format_money(profile.salary_cents)}",
                f"Премия: {format_money(profile.bonus_cents)}",
                f"Цель: {format_money(month.month_settings.target_cents)}",
            ]
        )
    elif section == "schedule":
        lines.extend(
            [
                f"Норма дня: {format_minutes(user.workday_minutes)}",
                f"Начало дня: {user.work_start_time:%H:%M}",
                f"Часовой пояс: {user.timezone}",
            ]
        )
    elif section == "payment":
        lines.extend(
            [
                f"Правило переработки: {profile.overtime_rule}",
                f"База ставки: {profile.rate_basis}",
                f"Своя ставка: {format_money(profile.custom_rate_cents)}/ч",
                f"Недоработка: {profile.underwork_mode}",
                f"Округление: {profile.rounding_minutes} мин",
            ]
        )
    elif section == "multipliers":
        lines.extend(
            [
                f"Будни: ×{profile.weekday_multiplier_percent / 100:g}",
                f"Суббота: ×{profile.saturday_multiplier_percent / 100:g}",
                f"Воскресенье: ×{profile.sunday_multiplier_percent / 100:g}",
                f"Праздник: ×{profile.holiday_multiplier_percent / 100:g}",
            ]
        )
    elif section == "goal":
        lines.extend(
            [
                f"Лимит будня: {format_minutes(user.max_weekday_overtime_minutes)}",
                f"Лимит суббот: {user.max_saturdays}",
                f"Рабочая суббота: {format_minutes(user.saturday_minutes)}",
                f"Воскресенье: {'разрешено' if user.allow_sunday else 'запрещено'}",
            ]
        )
    elif section == "reminders":
        lines.extend(
            [
                f"Состояние: {'включены' if reminder.enabled else 'выключены'}",
                f"Приход: {reminder.arrival_time:%H:%M}" if reminder.arrival_time else "Приход: отключён",
                f"Уход: {format_minutes(reminder.departure_after_minutes or 0)} после начала",
                (
                    f"Контроль смены: {reminder.open_shift_time:%H:%M}"
                    if reminder.open_shift_time
                    else "Контроль смены: отключён"
                ),
                f"Лимит перерыва: {reminder.open_break_minutes or 0} мин",
            ]
        )
    else:
        config = context.config
        lines.extend(
            [
                f"Автоматический приход: {'включён' if config.geofence_enabled else 'выключен'}",
                f"Зона: {config.geofence_zone}",
                f"Окно прихода: {config.geofence_arrival_start:%H:%M}–{config.geofence_arrival_end:%H:%M}",
                "",
                "Параметры геозоны меняются в переменных окружения Railway.",
            ]
        )
    return "\n".join(lines)


def _positive_money(value: str) -> int:
    cents = round(float(value) * 100)
    if cents <= 0:
        raise ValueError("сумма должна быть положительной")
    return cents


def _positive_hours(value: str) -> int:
    minutes = round(float(value) * 60)
    if minutes <= 0:
        raise ValueError("время должно быть положительным")
    return minutes


def _non_negative_int(value: str) -> int:
    result = int(value)
    if result < 0:
        raise ValueError("значение не может быть отрицательным")
    return result
