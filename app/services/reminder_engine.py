from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot

from app.context import AppContext
from app.database.enums import ReminderType
from app.services.reports import build_week_report
from app.services.time_tracking import session_work_minutes, total_break_minutes

logger = logging.getLogger(__name__)


class ReminderEngine:
    def __init__(self, bot: Bot, context: AppContext, interval_seconds: int):
        self.bot = bot
        self.context = context
        self.interval_seconds = interval_seconds

    async def run(self) -> None:
        # цикл напоминания
        while True:
            try:
                await self._process_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Reminder cycle failed", extra={"event": "reminder_cycle_failed"})
            await asyncio.sleep(self.interval_seconds)

    async def _process_all(self) -> None:
        for user_id in await self.context.users.list_ids():
            try:
                await self._process_user(user_id)
            except Exception:
                logger.exception(
                    "Reminder processing failed",
                    extra={"event": "reminder_user_failed", "user_id": user_id},
                )

    async def _process_user(self, user_id: int) -> None:
        settings = await self.context.users.get_reminder_settings(user_id)
        if not settings.enabled:
            return
        user, calendar_day, today_sessions, now_local = await self.context.analysis.today(user_id)
        active = next((item for item in today_sessions if item.ended_at_utc is None), None)

        if (
            settings.arrival_time
            and calendar_day.expected_minutes > 0
            and not today_sessions
            and now_local.time() >= settings.arrival_time
        ):
            await self._send_once(
                user_id,
                ReminderType.ARRIVAL,
                f"{now_local.date()}",
                "⏰ Рабочий день ещё не начат.\n\nНажмите «🟢 Пришёл», когда начнёте работу.",
            )

        if active and settings.departure_after_minutes:
            worked = session_work_minutes(active, datetime.now(UTC))
            if worked >= settings.departure_after_minutes:
                await self._send_once(
                    user_id,
                    ReminderType.DEPARTURE,
                    f"{active.id}",
                    f"⏰ Норма смены выполнена: {worked // 60} ч {worked % 60} мин.\n\n"
                    "Не забудьте завершить рабочий день.",
                )

        if active and settings.open_shift_time and now_local.time() >= settings.open_shift_time:
            await self._send_once(
                user_id,
                ReminderType.OPEN_SHIFT,
                f"{active.id}:{now_local.date()}",
                "⚠️ Рабочая смена всё ещё открыта.",
            )

        if active and settings.open_break_minutes:
            active_break = next((item for item in active.breaks if item.ended_at_utc is None), None)
            if active_break and total_break_minutes(active) >= settings.open_break_minutes:
                await self._send_once(
                    user_id,
                    ReminderType.OPEN_BREAK,
                    f"{active_break.id}",
                    "☕ Перерыв всё ещё открыт. Не забудьте продолжить работу.",
                )

        if (
            settings.weekly_report_weekday is not None
            and settings.weekly_report_time
            and now_local.weekday() == settings.weekly_report_weekday
            and now_local.time() >= settings.weekly_report_time
        ):
            bundle = await self.context.analysis.month(user_id)
            await self._send_once(
                user_id,
                ReminderType.WEEKLY_REPORT,
                f"{now_local.date().isocalendar().year}:{now_local.date().isocalendar().week}",
                build_week_report(bundle.analysis, bundle.now_local),
            )

    async def _send_once(
        self,
        user_id: int,
        reminder_type: str,
        delivery_key: str,
        text: str,
    ) -> None:
        if await self.context.reminders.was_sent(user_id, reminder_type, delivery_key):
            return
        await self.bot.send_message(user_id, text)
        await self.context.reminders.mark_sent(user_id, reminder_type, delivery_key)
        logger.info(
            "Reminder sent",
            extra={
                "event": "reminder_sent",
                "user_id": user_id,
                "reminder_type": reminder_type,
            },
        )
