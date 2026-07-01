from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.database.models import CalendarDay, MonthlySettings, PayProfile, UserSettings, WorkSession
from app.repositories.calendar import CalendarRepository
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from app.services.payroll import MonthAnalysis, calculate_month_analysis
from app.utils.formatters import month_bounds


@dataclass(slots=True)
class AnalysisBundle:
    user: UserSettings
    profile: PayProfile
    month_settings: MonthlySettings
    calendar_days: list[CalendarDay]
    sessions: list[WorkSession]
    analysis: MonthAnalysis
    now_local: datetime


class AnalysisUseCase:
    def __init__(
        self,
        users: UserRepository,
        calendar_repository: CalendarRepository,
        sessions: SessionRepository,
    ):
        self.users = users
        self.calendar = calendar_repository
        self.sessions = sessions

    async def month(self, user_id: int, now_utc: datetime | None = None) -> AnalysisBundle:
        # анализ месяца
        current_utc = now_utc or datetime.now(UTC)
        user = await self.users.get(user_id)
        profile = await self.users.get_pay_profile(user_id)
        zone = ZoneInfo(user.timezone)
        now_local = current_utc.astimezone(zone)
        year, month = now_local.year, now_local.month
        month_settings = await self.users.get_month(user_id, year, month)
        await self.calendar.ensure_month(user_id, year, month, user.workday_minutes)
        first, last = month_bounds(year, month)
        calendar_days = await self.calendar.get_range(user_id, first, last)
        start_utc = datetime.combine(first, time.min, tzinfo=zone).astimezone(UTC)
        end_utc = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        sessions = await self.sessions.list_range(user_id, start_utc, end_utc)
        analysis = calculate_month_analysis(
            user,
            profile,
            month_settings,
            calendar_days,
            sessions,
            now_local,
        )
        return AnalysisBundle(
            user=user,
            profile=profile,
            month_settings=month_settings,
            calendar_days=calendar_days,
            sessions=sessions,
            analysis=analysis,
            now_local=now_local,
        )

    async def today(
        self,
        user_id: int,
        now_utc: datetime | None = None,
    ) -> tuple[UserSettings, CalendarDay, list[WorkSession], datetime]:
        # анализ дня
        current_utc = now_utc or datetime.now(UTC)
        user = await self.users.get(user_id)
        zone = ZoneInfo(user.timezone)
        now_local = current_utc.astimezone(zone)
        await self.calendar.ensure_month(user_id, now_local.year, now_local.month, user.workday_minutes)
        calendar_day = await self.calendar.get_day(user_id, now_local.date())
        if calendar_day is None:
            raise RuntimeError("День календаря не найден.")
        start_utc = datetime.combine(now_local.date(), time.min, tzinfo=zone).astimezone(UTC)
        end_utc = datetime.combine(
            now_local.date() + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(UTC)
        sessions = await self.sessions.list_range(user_id, start_utc, end_utc)
        return user, calendar_day, sessions, now_local

    async def period_sessions(
        self,
        user_id: int,
        start: date,
        end: date,
    ) -> tuple[UserSettings, list[WorkSession]]:
        user = await self.users.get(user_id)
        zone = ZoneInfo(user.timezone)
        start_utc = datetime.combine(start, time.min, tzinfo=zone).astimezone(UTC)
        end_utc = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        return user, await self.sessions.list_range(user_id, start_utc, end_utc)
