from aiogram import F, Router
from aiogram.types import Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.main import MainButtons
from app.services.reports import build_payment_report

router = Router(name="payments")


@router.message(F.text == MainButtons.PAYMENTS)
async def payments_handler(message: Message, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    bundle = await context.analysis.month(user_id)
    schedules = await context.payments.list(user_id)
    await message.answer(build_payment_report(schedules, bundle.analysis, bundle.now_local))
