from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.database.database import Database
from app.handlers.helpers import ensure_user
from app.keyboards.inline import analytics_keyboard
from app.keyboards.main import MainButtons
from app.services.report_builder import build_month_report, build_period_report, get_week_bounds
from app.services.salary_calculator import calculate_month_analysis
from app.utils.formatters import day_bounds_utc, month_bounds_utc

router = Router(name="analytics")


@router.message(F.text == MainButtons.ANALYTICS)
async def analytics_menu_handler(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await message.answer("Выберите период анализа:", reply_markup=analytics_keyboard())


@router.callback_query(F.data.startswith("analytics:"))
async def analytics_callback_handler(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    user_id, user, now_local = await ensure_user(callback, db, config)
    period = callback.data.split(":", 1)[1]

    if period == "today":
        start_utc, end_utc = day_bounds_utc(now_local.date(), user.timezone)
        sessions = await db.list_sessions(user_id, start_utc, end_utc)
        norm = user.workday_minutes if now_local.weekday() < 5 else 0
        text = build_period_report("📊 Сегодня", sessions, user, norm, now_local)
    elif period == "week":
        start_day, end_day = get_week_bounds(now_local.date())
        zone = ZoneInfo(user.timezone)
        start_utc = datetime.combine(start_day, time.min, tzinfo=zone).astimezone(UTC)
        end_utc = datetime.combine(end_day, time.min, tzinfo=zone).astimezone(UTC)
        sessions = await db.list_sessions(user_id, start_utc, end_utc)
        elapsed_weekdays = sum(
            1
            for offset in range((now_local.date() - start_day).days + 1)
            if (start_day + timedelta(days=offset)).weekday() < 5
        )
        norm = elapsed_weekdays * user.workday_minutes
        text = build_period_report("📊 Текущая неделя", sessions, user, norm, now_local)
    else:
        month = await db.get_month_settings(user_id, now_local.year, now_local.month)
        start_utc, end_utc = month_bounds_utc(now_local.year, now_local.month, user.timezone)
        sessions = await db.list_sessions(user_id, start_utc, end_utc)
        analysis = calculate_month_analysis(user, month, sessions, now_local)
        text = build_month_report(analysis)

    if callback.message:
        await callback.message.answer(text)
