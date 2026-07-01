from datetime import UTC, datetime

from app.database.models import (
    CalendarDay,
    GeofenceEvent,
    MonthlySettings,
    PayProfile,
    PaySchedule,
    PendingShift,
    ReminderSettings,
    UserSettings,
    WorkBreak,
    WorkSession,
)
from app.database.tables import (
    CalendarDayTable,
    GeofenceEventTable,
    MonthlySettingsTable,
    PayProfileTable,
    PayScheduleTable,
    PendingShiftTable,
    ReminderSettingsTable,
    UserTable,
    WorkBreakTable,
    WorkSessionTable,
)


def to_user(row: UserTable) -> UserSettings:
    return UserSettings(
        telegram_id=row.telegram_id,
        timezone=row.timezone,
        workday_minutes=row.workday_minutes,
        work_start_time=row.work_start_time,
        default_target_cents=row.default_target_cents,
        max_weekday_overtime_minutes=row.max_weekday_overtime_minutes,
        max_saturdays=row.max_saturdays,
        saturday_minutes=row.saturday_minutes,
        allow_sunday=row.allow_sunday,
    )


def to_pay_profile(row: PayProfileTable) -> PayProfile:
    return PayProfile(
        user_id=row.user_id,
        salary_cents=row.salary_cents,
        bonus_cents=row.bonus_cents,
        overtime_rule=row.overtime_rule,
        rate_basis=row.rate_basis,
        custom_rate_cents=row.custom_rate_cents,
        underwork_mode=row.underwork_mode,
        weekday_multiplier_percent=row.weekday_multiplier_percent,
        saturday_multiplier_percent=row.saturday_multiplier_percent,
        sunday_multiplier_percent=row.sunday_multiplier_percent,
        holiday_multiplier_percent=row.holiday_multiplier_percent,
        rounding_minutes=row.rounding_minutes,
    )


def to_month(row: MonthlySettingsTable) -> MonthlySettings:
    return MonthlySettings(
        user_id=row.user_id,
        year=row.year,
        month=row.month,
        target_cents=row.target_cents,
        standard_minutes_override=row.standard_minutes_override,
    )


def to_calendar_day(row: CalendarDayTable) -> CalendarDay:
    return CalendarDay(
        id=row.id,
        user_id=row.user_id,
        work_date=row.work_date,
        day_type=row.day_type,
        expected_minutes=row.expected_minutes,
        is_paid=row.is_paid,
        comment=row.comment,
    )


def to_break(row: WorkBreakTable) -> WorkBreak:
    return WorkBreak(
        id=row.id,
        session_id=row.session_id,
        started_at_utc=_as_utc(row.started_at_utc),
        ended_at_utc=_as_utc(row.ended_at_utc) if row.ended_at_utc else None,
    )


def to_session(row: WorkSessionTable) -> WorkSession:
    breaks = [to_break(item) for item in sorted(row.breaks, key=lambda value: value.started_at_utc)]
    return WorkSession(
        id=row.id,
        user_id=row.user_id,
        started_at_utc=_as_utc(row.started_at_utc),
        ended_at_utc=_as_utc(row.ended_at_utc) if row.ended_at_utc else None,
        note=row.note,
        deleted_at_utc=_as_utc(row.deleted_at_utc) if row.deleted_at_utc else None,
        created_at_utc=_as_utc(row.created_at_utc),
        updated_at_utc=_as_utc(row.updated_at_utc),
        breaks=breaks,
    )


def to_geofence_event(row: GeofenceEventTable) -> GeofenceEvent:
    return GeofenceEvent(
        id=row.id,
        user_id=row.user_id,
        pending_shift_id=row.pending_shift_id,
        zone=row.zone,
        event_type=row.event_type,
        occurred_at_utc=_as_utc(row.occurred_at_utc),
        client=row.client,
        status=row.status,
    )


def to_pending_shift(row: PendingShiftTable) -> PendingShift:
    return PendingShift(
        id=row.id,
        user_id=row.user_id,
        local_date=row.local_date,
        suggested_start_utc=_as_utc(row.suggested_start_utc) if row.suggested_start_utc else None,
        suggested_end_utc=_as_utc(row.suggested_end_utc) if row.suggested_end_utc else None,
        status=row.status,
        telegram_chat_id=row.telegram_chat_id,
        telegram_message_id=row.telegram_message_id,
        work_session_id=row.work_session_id,
        created_at_utc=_as_utc(row.created_at_utc),
        updated_at_utc=_as_utc(row.updated_at_utc),
        processed_at_utc=_as_utc(row.processed_at_utc) if row.processed_at_utc else None,
    )


def to_reminder_settings(row: ReminderSettingsTable) -> ReminderSettings:
    return ReminderSettings(
        user_id=row.user_id,
        enabled=row.enabled,
        arrival_time=row.arrival_time,
        departure_after_minutes=row.departure_after_minutes,
        open_shift_time=row.open_shift_time,
        open_break_minutes=row.open_break_minutes,
        weekly_report_weekday=row.weekly_report_weekday,
        weekly_report_time=row.weekly_report_time,
    )


def to_pay_schedule(row: PayScheduleTable) -> PaySchedule:
    return PaySchedule(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        day_rule=row.day_rule,
        fixed_day=row.fixed_day,
        amount_cents=row.amount_cents,
        include_overtime=row.include_overtime,
        enabled=row.enabled,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
