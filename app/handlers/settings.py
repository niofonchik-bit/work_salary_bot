from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import edit_or_answer, ensure_user
from app.keyboards.inline import (
    overtime_mode_keyboard,
    settings_keyboard,
    weekend_multiplier_keyboard,
)
from app.keyboards.main import MainButtons
from app.services.salary_calculator import calculate_hourly_rate_cents, calculate_standard_minutes
from app.states.forms import SettingsStates
from app.utils.formatters import (
    format_duration,
    format_money,
    format_rate,
    get_zoneinfo,
    parse_duration_to_minutes,
    parse_money_to_cents,
)

router = Router(name="settings")


@router.message(F.text == MainButtons.SETTINGS)
async def settings_menu_handler(message: Message, db: Database, config: Config) -> None:
    user_id, user, now_local = await ensure_user(message, db, config)
    month = await db.get_month_settings(user_id, now_local.year, now_local.month)
    await message.answer(
        _build_settings_text(user, month),
        reply_markup=settings_keyboard(user),
    )


@router.callback_query(F.data == "settings:open")
async def settings_open_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    user_id, user, now_local = await ensure_user(callback, db, config)
    month = await db.get_month_settings(user_id, now_local.year, now_local.month)
    await edit_or_answer(callback, _build_settings_text(user, month), settings_keyboard(user))


@router.callback_query(F.data == "settings:overtime")
async def overtime_menu_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await edit_or_answer(
        callback,
        "<b>Как рассчитывать часовую ставку переработки?</b>",
        overtime_mode_keyboard(),
    )


@router.callback_query(F.data.startswith("overtime:"))
async def overtime_mode_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    await callback.answer()
    mode = callback.data.split(":", 1)[1]
    if mode == "custom":
        await state.set_state(SettingsStates.value)
        await state.update_data(field="custom_rate_cents")
        if callback.message:
            await callback.message.answer(
                "Введите чистую ставку за час в рублях, например <code>362,5</code>:"
            )
        return

    user_id, _, _ = await ensure_user(callback, db, config)
    await db.update_user_setting(user_id, "overtime_mode", mode)
    await edit_or_answer(callback, "Способ расчёта переработки обновлён ✅")


@router.callback_query(F.data == "settings:weekend")
async def weekend_menu_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await edit_or_answer(
        callback,
        "Выберите коэффициент оплаты часов в субботу и воскресенье:",
        weekend_multiplier_keyboard(),
    )


@router.callback_query(F.data.startswith("weekend:"))
async def weekend_value_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    multiplier = float(callback.data.split(":", 1)[1])
    user_id, _, _ = await ensure_user(callback, db, config)
    await db.update_user_setting(user_id, "weekend_multiplier", multiplier)
    await edit_or_answer(callback, f"Коэффициент выходных установлен: <b>×{multiplier:g}</b> ✅")


@router.callback_query(
    F.data.in_(
        {
            "settings:salary",
            "settings:bonus",
            "settings:target",
            "settings:workday",
            "settings:standard",
            "settings:timezone",
        }
    )
)
async def settings_input_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    field = callback.data.split(":", 1)[1]
    prompts = {
        "salary": "Введите чистую зарплату в рублях, например <code>26100</code>:",
        "bonus": "Введите чистую премию в рублях, например <code>34800</code>:",
        "target": "Введите цель по доходу в рублях, например <code>80000</code>:",
        "workday": (
            "Введите длительность рабочего дня: <code>8</code>, <code>8:30</code> или <code>8ч30м</code>:"
        ),
        "standard": "Введите норму текущего месяца: часы числом или <code>auto</code> для автоподсчёта:",
        "timezone": "Введите часовой пояс IANA, например <code>Europe/Istanbul</code>:",
    }
    await state.set_state(SettingsStates.value)
    await state.update_data(field=field)
    if callback.message:
        await callback.message.answer(prompts[field])


@router.message(SettingsStates.value)
async def settings_input_value_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    data = await state.get_data()
    field = data.get("field")
    raw = (message.text or "").strip()

    try:
        user_id, _, now_local = await ensure_user(message, db, config)
        if field in {"salary", "bonus", "target"}:
            cents = parse_money_to_cents(raw)
            mapping = {
                "salary": ("default_salary_cents", "salary_cents"),
                "bonus": ("default_bonus_cents", "bonus_cents"),
                "target": ("default_target_cents", "target_cents"),
            }
            user_field, month_field = mapping[field]
            await db.update_user_setting(user_id, user_field, cents)
            await db.update_month_setting(user_id, now_local.year, now_local.month, month_field, cents)
            result = format_money(cents)
        elif field == "workday":
            minutes = parse_duration_to_minutes(raw)
            if minutes <= 0 or minutes > 24 * 60:
                raise ValueError("Норма дня должна быть больше 0 и не больше 24 часов")
            await db.update_user_setting(user_id, "workday_minutes", minutes)
            result = format_duration(minutes)
        elif field == "standard":
            if raw.lower() in {"auto", "авто"}:
                await db.update_month_setting(
                    user_id, now_local.year, now_local.month, "standard_minutes", None
                )
                result = "автоматически"
            else:
                minutes = parse_duration_to_minutes(raw)
                if minutes <= 0:
                    raise ValueError("Норма месяца должна быть больше 0")
                await db.update_month_setting(
                    user_id, now_local.year, now_local.month, "standard_minutes", minutes
                )
                result = format_duration(minutes)
        elif field == "timezone":
            get_zoneinfo(raw)
            await db.update_user_setting(user_id, "timezone", raw)
            result = raw
        elif field == "custom_rate_cents":
            cents = parse_money_to_cents(raw)
            if cents <= 0:
                raise ValueError("Ставка должна быть больше 0")
            await db.update_user_setting(user_id, "custom_rate_cents", cents)
            await db.update_user_setting(user_id, "overtime_mode", "custom")
            result = format_money(cents) + "/ч"
        else:
            raise ValueError("Неизвестная настройка")
    except ValueError as error:
        await message.answer(str(error))
        return

    await state.clear()
    await message.answer(f"Настройка сохранена: <b>{result}</b> ✅")


def _build_settings_text(user, month) -> str:
    standard = calculate_standard_minutes(
        month.year,
        month.month,
        user.workday_minutes,
        month.standard_minutes,
    )
    rate = calculate_hourly_rate_cents(user, month, standard)
    mode_names = {
        "total": "зарплата + премия",
        "salary": "только зарплата",
        "custom": "своя ставка",
    }
    standard_note = "вручную" if month.standard_minutes is not None else "авто"
    return (
        "<b>⚙️ Настройки</b>\n\n"
        f"Зарплата: <b>{format_money(month.salary_cents)}</b>\n"
        f"Премия: <b>{format_money(month.bonus_cents)}</b>\n"
        f"Цель: <b>{format_money(month.target_cents)}</b>\n"
        f"Рабочий день: {format_duration(user.workday_minutes)}\n"
        f"Норма месяца: {format_duration(standard)} ({standard_note})\n"
        f"Переработка: {mode_names[user.overtime_mode]}\n"
        f"Расчётная ставка: {format_rate(rate)}\n"
        f"Выходные: ×{user.weekend_multiplier:g}\n"
        f"Часовой пояс: <code>{user.timezone}</code>"
    )
