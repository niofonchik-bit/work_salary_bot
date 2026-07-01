from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.main import main_keyboard

router = Router(name="common")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    await ensure_user(message, context)
    await state.clear()
    await context.ui.show(
        message,
        _home_text(),
        reply_markup=main_keyboard(),
        force_new=True,
    )


@router.message(Command("help"))
async def help_handler(message: Message, context: AppContext) -> None:
    await context.ui.show(
        message,
        "<b>Основные действия</b>\n\n"
        "• «Пришёл» — начало смены\n"
        "• «Ушёл» — завершение смены\n"
        "• «Перерыв» — начало или завершение перерыва\n"
        "• «Анализ» — зарплата, баланс и план цели\n"
        "• «Календарь» — отпуск, больничный и выходной\n"
        "• /cancel — отмена текущего ввода\n\n"
        "Сообщения меню обновляются на одном экране, поэтому история чата не захламляется.",
    )


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    await state.clear()
    await context.ui.show(message, "Действие отменено.\n\n" + _home_text())


@router.message(Command("status"))
async def status_handler(message: Message, context: AppContext) -> None:
    user_id = message.from_user.id
    if context.config.admin_user_id is None or user_id != context.config.admin_user_id:
        await context.ui.show(message, "Команда доступна только администратору.")
        return
    database_ok = await context.database.ping()
    user_count = len(await context.users.list_ids())
    await context.ui.show(
        message,
        "<b>Состояние приложения</b>\n\n"
        f"База данных: {'доступна' if database_ok else 'недоступна'}\n"
        f"Пользователей: {user_count}\n"
        f"Геозона: {'включена' if context.config.geofence_enabled else 'выключена'}",
    )


@router.message(Command("myid"))
async def my_id_handler(message: Message, context: AppContext) -> None:
    await context.ui.show(message, f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.callback_query(F.data == "ui:dismiss")
async def dismiss_handler(callback: CallbackQuery, context: AppContext) -> None:
    await context.ui.delete(callback.message if isinstance(callback.message, Message) else None)
    await callback.answer()


def _home_text() -> str:
    return (
        "<b>Рабочее время и зарплата</b>\n\n"
        "Фиксируйте смены, перерывы и цели. Полный расчёт открывается только из меню."
    )
