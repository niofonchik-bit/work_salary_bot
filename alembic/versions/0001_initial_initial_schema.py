"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-01 07:34:11.910562
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # начальная схема
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fsm_states",
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=300), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("storage_key"),
    )
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("timezone", sa.String(length=128), nullable=False),
        sa.Column("workday_minutes", sa.Integer(), nullable=False),
        sa.Column("work_start_time", sa.Time(), nullable=False),
        sa.Column("default_target_cents", sa.BigInteger(), nullable=False),
        sa.Column("max_weekday_overtime_minutes", sa.Integer(), nullable=False),
        sa.Column("max_saturdays", sa.Integer(), nullable=False),
        sa.Column("saturday_minutes", sa.Integer(), nullable=False),
        sa.Column("allow_sunday", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_saturdays >= 0", name="ck_users_max_saturdays"),
        sa.CheckConstraint("max_weekday_overtime_minutes >= 0", name="ck_users_max_weekday_overtime"),
        sa.CheckConstraint("saturday_minutes >= 0", name="ck_users_saturday_minutes"),
        sa.CheckConstraint("workday_minutes > 0", name="ck_users_workday_minutes"),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_table(
        "calendar_days",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("day_type", sa.String(length=24), nullable=False),
        sa.Column("expected_minutes", sa.Integer(), nullable=False),
        sa.Column("is_paid", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "day_type IN ('workday', 'weekend', 'holiday', 'vacation', "
            "'sick_leave', 'unpaid_leave', 'day_off', 'shifted_workday')",
            name="ck_calendar_days_day_type",
        ),
        sa.CheckConstraint("expected_minutes >= 0", name="ck_calendar_days_expected_minutes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "work_date", name="uq_calendar_days_user_date"),
    )
    op.create_index("idx_calendar_days_user_date", "calendar_days", ["user_id", "work_date"], unique=False)
    op.create_table(
        "monthly_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("target_cents", sa.BigInteger(), nullable=False),
        sa.Column("standard_minutes_override", sa.Integer(), nullable=True),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_settings_month"),
        sa.CheckConstraint(
            "standard_minutes_override IS NULL OR standard_minutes_override > 0",
            name="ck_monthly_settings_standard_override",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "year", "month"),
    )
    op.create_table(
        "pay_profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("salary_cents", sa.BigInteger(), nullable=False),
        sa.Column("bonus_cents", sa.BigInteger(), nullable=False),
        sa.Column("overtime_rule", sa.String(length=16), nullable=False),
        sa.Column("rate_basis", sa.String(length=16), nullable=False),
        sa.Column("custom_rate_cents", sa.BigInteger(), nullable=False),
        sa.Column("underwork_mode", sa.String(length=16), nullable=False),
        sa.Column("weekday_multiplier_percent", sa.Integer(), nullable=False),
        sa.Column("saturday_multiplier_percent", sa.Integer(), nullable=False),
        sa.Column("sunday_multiplier_percent", sa.Integer(), nullable=False),
        sa.Column("holiday_multiplier_percent", sa.Integer(), nullable=False),
        sa.Column("rounding_minutes", sa.Integer(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "overtime_rule IN ('daily', 'monthly', 'balance')", name="ck_pay_profiles_overtime_rule"
        ),
        sa.CheckConstraint("rate_basis IN ('total', 'salary', 'custom')", name="ck_pay_profiles_rate_basis"),
        sa.CheckConstraint("underwork_mode IN ('ignore', 'deduct')", name="ck_pay_profiles_underwork_mode"),
        sa.CheckConstraint("rounding_minutes IN (1, 5, 10, 15, 30)", name="ck_pay_profiles_rounding"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "pay_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("day_rule", sa.String(length=20), nullable=False),
        sa.Column("fixed_day", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("include_overtime", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "day_rule IN ('fixed_day', 'last_day', 'last_workday')", name="ck_pay_schedules_day_rule"
        ),
        sa.CheckConstraint("fixed_day IS NULL OR fixed_day BETWEEN 1 AND 31", name="ck_pay_schedules_day"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "title", name="uq_pay_schedules_user_title"),
    )
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column("delivery_key", sa.String(length=100), nullable=False),
        sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "reminder_type", "delivery_key", name="uq_reminder_deliveries_key"),
    )
    op.create_table(
        "reminder_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("arrival_time", sa.Time(), nullable=True),
        sa.Column("departure_after_minutes", sa.Integer(), nullable=True),
        sa.Column("open_shift_time", sa.Time(), nullable=True),
        sa.Column("open_break_minutes", sa.Integer(), nullable=True),
        sa.Column("weekly_report_weekday", sa.Integer(), nullable=True),
        sa.Column("weekly_report_time", sa.Time(), nullable=True),
        sa.CheckConstraint(
            "departure_after_minutes IS NULL OR departure_after_minutes > 0",
            name="ck_reminders_departure_minutes",
        ),
        sa.CheckConstraint(
            "weekly_report_weekday IS NULL OR weekly_report_weekday BETWEEN 0 AND 6",
            name="ck_reminders_weekday",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "work_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("deleted_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ended_at_utc IS NULL OR ended_at_utc > started_at_utc", name="ck_work_sessions_time_order"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_one_active_session_per_user",
        "work_sessions",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
        postgresql_where=sa.text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
    )
    op.create_index(
        "idx_work_sessions_user_start", "work_sessions", ["user_id", "started_at_utc"], unique=False
    )
    op.create_table(
        "work_breaks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ended_at_utc IS NULL OR ended_at_utc > started_at_utc", name="ck_work_breaks_time_order"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["work_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_one_active_break_per_session",
        "work_breaks",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text("ended_at_utc IS NULL"),
        postgresql_where=sa.text("ended_at_utc IS NULL"),
    )
    op.create_index(
        "idx_work_breaks_session_start", "work_breaks", ["session_id", "started_at_utc"], unique=False
    )


def downgrade() -> None:
    # удаление схемы
    op.drop_index("idx_work_breaks_session_start", table_name="work_breaks")
    op.drop_index(
        "idx_one_active_break_per_session",
        table_name="work_breaks",
        sqlite_where=sa.text("ended_at_utc IS NULL"),
        postgresql_where=sa.text("ended_at_utc IS NULL"),
    )
    op.drop_table("work_breaks")
    op.drop_index("idx_work_sessions_user_start", table_name="work_sessions")
    op.drop_index(
        "idx_one_active_session_per_user",
        table_name="work_sessions",
        sqlite_where=sa.text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
        postgresql_where=sa.text("ended_at_utc IS NULL AND deleted_at_utc IS NULL"),
    )
    op.drop_table("work_sessions")
    op.drop_table("reminder_settings")
    op.drop_table("reminder_deliveries")
    op.drop_table("pay_schedules")
    op.drop_table("pay_profiles")
    op.drop_table("monthly_settings")
    op.drop_index("idx_calendar_days_user_date", table_name="calendar_days")
    op.drop_table("calendar_days")
    op.drop_table("users")
    op.drop_table("fsm_states")
    op.drop_table("audit_events")
