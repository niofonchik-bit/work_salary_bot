from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.context import AppContext
from app.handlers.helpers import ensure_user
from app.keyboards.inline import export_keyboard
from app.keyboards.main import MainButtons
from app.services.exports import build_csv_export, build_json_export

router = Router(name="export")


@router.message(F.text == MainButtons.EXPORT)
async def export_handler(message: Message, state: FSMContext, context: AppContext) -> None:
    await state.clear()
    await context.ui.show(
        message,
        "<b>📤 Экспорт</b>\n\nВыберите формат. Сам файл останется в чате как полезный результат.",
        reply_markup=export_keyboard(),
    )


@router.callback_query(F.data.startswith("export:"))
async def export_callback(callback: CallbackQuery, context: AppContext) -> None:
    user_id = await ensure_user(callback, context)
    bundle = await context.analysis.month(user_id)
    kind = callback.data.rsplit(":", 1)[1]
    if kind == "csv":
        content = build_csv_export(bundle.sessions, bundle.user)
        filename = f"work-{bundle.analysis.year}-{bundle.analysis.month:02d}.csv"
    else:
        content = build_json_export(bundle.user, bundle.calendar_days, bundle.sessions)
        filename = f"backup-{bundle.analysis.year}-{bundle.analysis.month:02d}.json"
    if callback.message:
        await callback.message.answer_document(BufferedInputFile(content, filename=filename))
    await context.ui.show(
        callback,
        f"✅ Файл <code>{filename}</code> отправлен.\n\nВыберите другой формат при необходимости.",
        reply_markup=export_keyboard(),
    )
    await callback.answer("Файл отправлен.")
