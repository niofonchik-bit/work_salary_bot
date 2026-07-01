from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import ensure_user
from app.keyboards.inline import goal_keyboard
from app.keyboards.main import MainButtons
from app.states.forms import GoalStates
from app.utils.formatters import format_money, parse_money_to_cents

router = Router(name="goals")


@router.message(F.text == MainButtons.GOAL)
async def goal_menu_handler(message: Message, db: Database, config: Config) -> None:
    user_id, _, now_local = await ensure_user(message, db, config)
    month = await db.get_month_settings(user_id, now_local.year, now_local.month)
    await message.answer(
        f"Текущая цель: <b>{format_money(month.target_cents)}</b>\nВыберите новую цель:",
        reply_markup=goal_keyboard(),
    )


@router.callback_query(F.data.startswith("goal:set:"))
async def goal_set_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    user_id, _, now_local = await ensure_user(callback, db, config)
    rubles = int(callback.data.rsplit(":", 1)[1])
    cents = rubles * 100
    await db.update_user_setting(user_id, "default_target_cents", cents)
    await db.update_month_setting(user_id, now_local.year, now_local.month, "target_cents", cents)
    if callback.message:
        await callback.message.edit_text(f"Цель установлена: <b>{format_money(cents)}</b> ✅")


@router.callback_query(F.data == "goal:custom")
async def goal_custom_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(GoalStates.custom_value)
    if callback.message:
        await callback.message.answer("Введите цель в рублях, например <code>85000</code>:")


@router.message(GoalStates.custom_value)
async def goal_custom_value_handler(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
) -> None:
    try:
        cents = parse_money_to_cents(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return

    user_id, _, now_local = await ensure_user(message, db, config)
    await db.update_user_setting(user_id, "default_target_cents", cents)
    await db.update_month_setting(user_id, now_local.year, now_local.month, "target_cents", cents)
    await state.clear()
    await message.answer(f"Цель установлена: <b>{format_money(cents)}</b> ✅")
