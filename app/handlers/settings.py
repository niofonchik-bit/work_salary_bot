from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import choice_keyboard, settings_keyboard
from app.keyboards.main import MainButtons
from app.states.forms import SettingForm
from app.utils.formatters import format_minutes, format_money

router = Router(name="settings")


@router.message(F.text == MainButtons.SETTINGS)
async def settings_handler(message: Message, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await message.answer(await _settings_text(context, user_id), reply_markup=settings_keyboard())


@router.callback_query(F.data == "settings:overtime_rule")
async def overtime_rule_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Выберите правило переработки:",
        reply_markup=choice_keyboard(
            "settings_set:overtime_rule",
            [
                ("По каждому дню", "daily"),
                ("После нормы месяца", "monthly"),
                ("По балансу на сегодня", "balance"),
            ],
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:rate_basis")
async def rate_basis_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Выберите базу часовой ставки:",
        reply_markup=choice_keyboard(
            "settings_set:rate_basis",
            [
                ("Зарплата + премия", "total"),
                ("Только зарплата", "salary"),
                ("Своя ставка", "custom"),
            ],
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:underwork")
async def underwork_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Как учитывать недоработку:",
        reply_markup=choice_keyboard(
            "settings_set:underwork_mode",
            [("Не уменьшать прогноз", "ignore"), ("Уменьшать прогноз", "deduct")],
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:reminders")
async def reminders_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Состояние напоминаний:",
        reply_markup=choice_keyboard(
            "settings_set:reminders",
            [("Включить", "on"), ("Выключить", "off")],
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:allow_sunday")
async def allow_sunday_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Работа по воскресеньям:",
        reply_markup=choice_keyboard(
            "settings_set:allow_sunday",
            [("Разрешить", "on"), ("Запретить", "off")],
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:rounding")
async def rounding_handler(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Шаг округления рабочего времени:",
        reply_markup=choice_keyboard(
            "settings_set:rounding_minutes",
            [(f"{value} мин", str(value)) for value in (1, 5, 10, 15, 30)],
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_set:"))
async def settings_choice_handler(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    _, field, value = callback.data.split(":", 2)
    if field == "reminders":
        await context.users.update_reminder_settings(user_id, "enabled", value == "on")
    elif field == "allow_sunday":
        await context.users.update(user_id, "allow_sunday", value == "on")
    elif field == "rounding_minutes":
        await context.users.update_pay_profile(user_id, field, int(value))
    else:
        await context.users.update_pay_profile(user_id, field, value)
    await callback.answer("Настройка сохранена.")
    await callback.message.answer(await _settings_text(context, user_id), reply_markup=settings_keyboard())


@router.callback_query(F.data.startswith("settings:"))
async def settings_input_handler(
    callback: CallbackQuery,
    state: FSMContext,
    context: AppContext,
) -> None:
    await ensure_user(callback, context)
    field = callback.data.split(":", 1)[1]
    prompts = {
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
    prompt = prompts.get(field)
    if prompt is None:
        await callback.answer()
        return
    await state.set_state(SettingForm.value)
    await state.update_data(setting=field)
    await callback.message.answer(prompt)
    await callback.answer()


@router.message(SettingForm.value)
async def settings_value_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    data = await state.get_data()
    field = data.get("setting")
    try:
        await _save_value(context, user_id, str(field), message.text.strip())
    except (ValueError, ZoneInfoNotFoundError) as error:
        await message.answer(f"Некорректное значение: {error}")
        return
    await state.clear()
    text = "Настройка сохранена.\n\n" + await _settings_text(context, user_id)
    await message.answer(text, reply_markup=settings_keyboard())


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


async def _settings_text(context: AppContext, user_id: int) -> str:
    user = await context.users.get(user_id)
    profile = await context.users.get_pay_profile(user_id)
    month = await context.analysis.month(user_id)
    reminder = await context.users.get_reminder_settings(user_id)
    return "\n".join(
        [
            "<b>⚙️ Настройки</b>",
            "",
            f"Зарплата: {format_money(profile.salary_cents)}",
            f"Премия: {format_money(profile.bonus_cents)}",
            f"Цель: {format_money(month.month_settings.target_cents)}",
            f"Норма дня: {format_minutes(user.workday_minutes)}",
            f"Начало дня: {user.work_start_time:%H:%M}",
            f"Правило переработки: {profile.overtime_rule}",
            f"База ставки: {profile.rate_basis}",
            f"Своя ставка: {format_money(profile.custom_rate_cents)}/ч",
            f"Недоработка: {profile.underwork_mode}",
            f"Будни: ×{profile.weekday_multiplier_percent / 100:g}",
            f"Суббота: ×{profile.saturday_multiplier_percent / 100:g}",
            f"Воскресенье: ×{profile.sunday_multiplier_percent / 100:g}",
            f"Праздник: ×{profile.holiday_multiplier_percent / 100:g}",
            f"Округление: {profile.rounding_minutes} мин",
            f"Лимит будня: {format_minutes(user.max_weekday_overtime_minutes)}",
            f"Лимит суббот: {user.max_saturdays}",
            f"Рабочая суббота: {format_minutes(user.saturday_minutes)}",
            f"Воскресенье: {'разрешено' if user.allow_sunday else 'запрещено'}",
            f"Напоминания: {'включены' if reminder.enabled else 'выключены'}",
            f"Приход: {reminder.arrival_time:%H:%M}" if reminder.arrival_time else "Приход: отключён",
            f"Напоминание об уходе: {format_minutes(reminder.departure_after_minutes or 0)}",
            (
                f"Контроль смены: {reminder.open_shift_time:%H:%M}"
                if reminder.open_shift_time
                else "Контроль смены: отключён"
            ),
            f"Лимит перерыва: {reminder.open_break_minutes or 0} мин",
            f"Часовой пояс: {user.timezone}",
        ]
    )


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
