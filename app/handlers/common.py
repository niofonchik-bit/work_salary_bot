from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.main import main_keyboard

router = Router(name="common")


@router.message(Command("start"))
async def start_handler(message: Message, context: AppContext) -> None:
    await ensure_user(message, context)
    await message.answer(
        "<b>Рабочее время и зарплата</b>\n\n"
        "Фиксируйте смены, перерывы и цели. Полный расчёт открывается только из меню.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "<b>Основные действия</b>\n\n"
        "• «Пришёл» — начало смены\n"
        "• «Ушёл» — завершение смены\n"
        "• «Перерыв» — начало или завершение перерыва\n"
        "• «Анализ» — зарплата, баланс и план цели\n"
        "• «Календарь» — отпуск, больничный и выходной\n"
        "• /cancel — отмена текущего ввода"
    )


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ввод отменён.", reply_markup=main_keyboard())


@router.message(Command("status"))
async def status_handler(message: Message, context: AppContext) -> None:
    user_id = message.from_user.id
    if context.config.admin_user_id is None or user_id != context.config.admin_user_id:
        await message.answer("Команда доступна только администратору.")
        return
    database_ok = await context.database.ping()
    user_count = len(await context.users.list_ids())
    await message.answer(
        "<b>Состояние приложения</b>\n\n"
        f"База данных: {'доступна' if database_ok else 'недоступна'}\n"
        f"Пользователей: {user_count}"
    )


@router.message(Command("myid"))
async def my_id_handler(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")
