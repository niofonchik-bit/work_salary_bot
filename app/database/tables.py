from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserTable(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    workday_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    default_salary_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=2_610_000)
    default_bonus_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=3_480_000)
    default_target_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=8_000_000)
    overtime_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="total")
    custom_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    weekend_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "overtime_mode IN ('total', 'salary', 'custom')",
            name="ck_users_overtime_mode",
        ),
        CheckConstraint("workday_minutes > 0", name="ck_users_workday_minutes"),
        CheckConstraint("weekend_multiplier > 0", name="ck_users_weekend_multiplier"),
    )


class MonthlySettingsTable(Base):
    __tablename__ = "monthly_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    salary_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bonus_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    standard_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_settings_month"),
        CheckConstraint(
            "standard_minutes IS NULL OR standard_minutes > 0",
            name="ck_monthly_settings_standard_minutes",
        ),
    )


class WorkSessionTable(Base):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("break_minutes >= 0", name="ck_work_sessions_break_minutes"),
        CheckConstraint(
            "ended_at_utc IS NULL OR ended_at_utc > started_at_utc",
            name="ck_work_sessions_time_order",
        ),
        Index("idx_work_sessions_user_start", "user_id", "started_at_utc"),
        Index(
            "idx_one_active_session_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("ended_at_utc IS NULL"),
            postgresql_where=text("ended_at_utc IS NULL"),
        ),
    )
