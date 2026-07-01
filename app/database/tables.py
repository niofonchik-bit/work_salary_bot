from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserTable(Base):
    # таблица пользователя
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    workday_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    work_start_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    default_target_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=8_000_000)
    max_weekday_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    max_saturdays: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    saturday_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    allow_sunday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("workday_minutes > 0", name="ck_users_workday_minutes"),
        CheckConstraint("max_weekday_overtime_minutes >= 0", name="ck_users_max_weekday_overtime"),
        CheckConstraint("max_saturdays >= 0", name="ck_users_max_saturdays"),
        CheckConstraint("saturday_minutes >= 0", name="ck_users_saturday_minutes"),
    )


class PayProfileTable(Base):
    # таблица оплаты
    __tablename__ = "pay_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    salary_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=2_610_000)
    bonus_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=3_480_000)
    overtime_rule: Mapped[str] = mapped_column(String(16), nullable=False, default="balance")
    rate_basis: Mapped[str] = mapped_column(String(16), nullable=False, default="total")
    custom_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    underwork_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="ignore")
    weekday_multiplier_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    saturday_multiplier_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    sunday_multiplier_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    holiday_multiplier_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    rounding_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "overtime_rule IN ('daily', 'monthly', 'balance')",
            name="ck_pay_profiles_overtime_rule",
        ),
        CheckConstraint(
            "rate_basis IN ('total', 'salary', 'custom')",
            name="ck_pay_profiles_rate_basis",
        ),
        CheckConstraint(
            "underwork_mode IN ('ignore', 'deduct')",
            name="ck_pay_profiles_underwork_mode",
        ),
        CheckConstraint("rounding_minutes IN (1, 5, 10, 15, 30)", name="ck_pay_profiles_rounding"),
    )


class MonthlySettingsTable(Base):
    # таблица месяца
    __tablename__ = "monthly_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    standard_minutes_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_settings_month"),
        CheckConstraint(
            "standard_minutes_override IS NULL OR standard_minutes_override > 0",
            name="ck_monthly_settings_standard_override",
        ),
    )


class CalendarDayTable(Base):
    # таблица календаря
    __tablename__ = "calendar_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_type: Mapped[str] = mapped_column(String(24), nullable=False)
    expected_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment: Mapped[str | None] = mapped_column(String(300), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "work_date", name="uq_calendar_days_user_date"),
        CheckConstraint("expected_minutes >= 0", name="ck_calendar_days_expected_minutes"),
        CheckConstraint(
            "day_type IN ('workday', 'weekend', 'holiday', 'vacation', 'sick_leave', "
            "'unpaid_leave', 'day_off', 'shifted_workday')",
            name="ck_calendar_days_day_type",
        ),
        Index("idx_calendar_days_user_date", "user_id", "work_date"),
    )


class WorkSessionTable(Base):
    # таблица смены
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    breaks: Mapped[list[WorkBreakTable]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "ended_at_utc IS NULL OR ended_at_utc > started_at_utc",
            name="ck_work_sessions_time_order",
        ),
        Index("idx_work_sessions_user_start", "user_id", "started_at_utc"),
        Index(
            "idx_one_active_session_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
            postgresql_where=text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
        ),
    )


class WorkBreakTable(Base):
    # таблица перерыва
    __tablename__ = "work_breaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("work_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session: Mapped[WorkSessionTable] = relationship(back_populates="breaks")

    __table_args__ = (
        CheckConstraint(
            "ended_at_utc IS NULL OR ended_at_utc > started_at_utc",
            name="ck_work_breaks_time_order",
        ),
        Index("idx_work_breaks_session_start", "session_id", "started_at_utc"),
        Index(
            "idx_one_active_break_per_session",
            "session_id",
            unique=True,
            sqlite_where=text("ended_at_utc IS NULL"),
            postgresql_where=text("ended_at_utc IS NULL"),
        ),
    )


class PendingShiftTable(Base):
    # таблица ожидающей смены
    __tablename__ = "pending_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    suggested_start_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suggested_end_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    work_session_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("work_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting_arrival', 'waiting_departure', 'ready', 'attention', "
            "'confirmed', 'rejected')",
            name="ck_pending_shifts_status",
        ),
        Index(
            "idx_pending_shifts_user_status_date",
            "user_id",
            "status",
            "local_date",
        ),
        Index(
            "uq_pending_shifts_active_user_date",
            "user_id",
            "local_date",
            unique=True,
            sqlite_where=text("status IN ('waiting_arrival', 'waiting_departure', 'ready', 'attention')"),
            postgresql_where=text("status IN ('waiting_arrival', 'waiting_departure', 'ready', 'attention')"),
        ),
    )


class GeofenceEventTable(Base):
    # таблица события геозоны
    __tablename__ = "geofence_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    pending_shift_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pending_shifts.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('arrival', 'departure')",
            name="ck_geofence_events_type",
        ),
        CheckConstraint(
            "status IN ('recorded', 'duplicate', 'merged')",
            name="ck_geofence_events_status",
        ),
        Index("idx_geofence_events_user_time", "user_id", "occurred_at_utc"),
        Index("idx_geofence_events_pending", "pending_shift_id"),
    )


class ReminderSettingsTable(Base):
    # таблица напоминания
    __tablename__ = "reminder_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(9, 0))
    departure_after_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=480)
    open_shift_time: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(21, 0))
    open_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=60)
    weekly_report_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True, default=4)
    weekly_report_time: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(18, 0))

    __table_args__ = (
        CheckConstraint(
            "departure_after_minutes IS NULL OR departure_after_minutes > 0",
            name="ck_reminders_departure_minutes",
        ),
        CheckConstraint(
            "weekly_report_weekday IS NULL OR weekly_report_weekday BETWEEN 0 AND 6",
            name="ck_reminders_weekday",
        ),
    )


class ReminderDeliveryTable(Base):
    # таблица доставки
    __tablename__ = "reminder_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_key: Mapped[str] = mapped_column(String(100), nullable=False)
    sent_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "reminder_type",
            "delivery_key",
            name="uq_reminder_deliveries_key",
        ),
    )


class PayScheduleTable(Base):
    # таблица выплаты
    __tablename__ = "pay_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    day_rule: Mapped[str] = mapped_column(String(20), nullable=False)
    fixed_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    include_overtime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("user_id", "title", name="uq_pay_schedules_user_title"),
        CheckConstraint(
            "day_rule IN ('fixed_day', 'last_day', 'last_workday')",
            name="ck_pay_schedules_day_rule",
        ),
        CheckConstraint("fixed_day IS NULL OR fixed_day BETWEEN 1 AND 31", name="ck_pay_schedules_day"),
    )


class FsmStateTable(Base):
    # таблица состояния
    __tablename__ = "fsm_states"

    storage_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(300), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEventTable(Base):
    # таблица аудита
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
