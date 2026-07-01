from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import ensure_user
from app.keyboards.main import main_keyboard

router = Router(name="common")


@router.message(CommandStart())
async def start_handler(message: Message, db: Database, config: Config, state: FSMContext) -> None:
    await state.clear()
    _, settings, _ = await ensure_user(message, db, config)
    await message.answer(
        "<b>Учёт рабочего времени и зарплаты</b>\n\n"
        "Кнопки «Пришёл» и «Ушёл» фиксируют смену без лишних отчётов. "
        "Подробный расчёт открывается отдельно через раздел «Анализ».\n\n"
        f"Текущий часовой пояс: <code>{settings.timezone}</code>",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "<b>Основные команды</b>\n\n"
        "/start — открыть главное меню\n"
        "/cancel — отменить текущий ввод\n"
        "/myid — показать Telegram ID\n\n"
        "Сначала задайте зарплату, премию, цель и способ расчёта переработки в настройках."
    )


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    await state.clear()
    if current_state:
        await message.answer("Ввод отменён.", reply_markup=main_keyboard())
    else:
        await message.answer("Сейчас нет активного ввода.", reply_markup=main_keyboard())


@router.message(Command("myid"))
async def my_id_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")
