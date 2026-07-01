from datetime import UTC, datetime

from app.database.models import WorkBreak, WorkSession
from app.services.time_tracking import split_work_minutes_by_day


def test_session_is_split_across_local_midnight() -> None:
    session = WorkSession(
        id=1,
        user_id=1,
        started_at_utc=datetime(2026, 7, 1, 19, 0, tzinfo=UTC),
        ended_at_utc=datetime(2026, 7, 2, 3, 0, tzinfo=UTC),
        note=None,
        deleted_at_utc=None,
        created_at_utc=datetime(2026, 7, 1, 19, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 7, 2, 3, 0, tzinfo=UTC),
        breaks=[
            WorkBreak(
                id=1,
                session_id=1,
                started_at_utc=datetime(2026, 7, 1, 21, 30, tzinfo=UTC),
                ended_at_utc=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
            )
        ],
    )

    result = split_work_minutes_by_day([session], "Europe/Istanbul")

    assert result == {
        datetime(2026, 7, 1).date(): 120,
        datetime(2026, 7, 2).date(): 330,
    }
