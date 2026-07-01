from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.main import MainButtons
from app.services.reports import build_month_report

router = Router(name="analytics")


@router.message(F.text == MainButtons.ANALYTICS)
async def analytics_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    user_id = await ensure_user(message, context)
    await state.clear()
    bundle = await context.analysis.month(user_id)
    await context.ui.show(message, build_month_report(bundle.analysis))
