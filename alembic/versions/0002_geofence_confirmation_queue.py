"""geofence confirmation queue

Revision ID: 0002_geofence_queue
Revises: 0001_initial
Create Date: 2026-07-01 13:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0002_geofence_queue"
down_revision: str | None = "0001_initial"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # очередь подтверждения
    op.create_table(
        "pending_shifts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("suggested_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suggested_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("work_session_id", sa.Integer(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('waiting_arrival', 'waiting_departure', 'ready', 'attention', "
            "'confirmed', 'rejected')",
            name="ck_pending_shifts_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_session_id"], ["work_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_pending_shifts_user_date"),
    )
    op.create_index(
        "idx_pending_shifts_user_status_date",
        "pending_shifts",
        ["user_id", "status", "local_date"],
        unique=False,
    )
    op.create_table(
        "geofence_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pending_shift_id", sa.Integer(), nullable=False),
        sa.Column("zone", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("occurred_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('arrival', 'departure')",
            name="ck_geofence_events_type",
        ),
        sa.CheckConstraint(
            "status IN ('recorded', 'duplicate', 'merged')",
            name="ck_geofence_events_status",
        ),
        sa.ForeignKeyConstraint(["pending_shift_id"], ["pending_shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_geofence_events_pending",
        "geofence_events",
        ["pending_shift_id"],
        unique=False,
    )
    op.create_index(
        "idx_geofence_events_user_time",
        "geofence_events",
        ["user_id", "occurred_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    # удаление очереди
    op.drop_index("idx_geofence_events_user_time", table_name="geofence_events")
    op.drop_index("idx_geofence_events_pending", table_name="geofence_events")
    op.drop_table("geofence_events")
    op.drop_index("idx_pending_shifts_user_status_date", table_name="pending_shifts")
    op.drop_table("pending_shifts")
