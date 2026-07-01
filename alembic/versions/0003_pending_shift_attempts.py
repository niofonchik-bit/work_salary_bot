"""pending shift attempts

Revision ID: 0003_pending_attempts
Revises: 0002_geofence_queue
Create Date: 2026-07-01 15:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0003_pending_attempts"
down_revision: str | None = "0002_geofence_queue"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

_ACTIVE_STATUS_FILTER = "status IN ('waiting_arrival', 'waiting_departure', 'ready', 'attention')"


def upgrade() -> None:
    with op.batch_alter_table("pending_shifts") as batch_op:
        batch_op.drop_constraint(
            "uq_pending_shifts_user_date",
            type_="unique",
        )

    op.create_index(
        "uq_pending_shifts_active_user_date",
        "pending_shifts",
        ["user_id", "local_date"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_STATUS_FILTER),
        postgresql_where=sa.text(_ACTIVE_STATUS_FILTER),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_shifts_active_user_date",
        table_name="pending_shifts",
    )

    with op.batch_alter_table("pending_shifts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_pending_shifts_user_date",
            ["user_id", "local_date"],
        )
