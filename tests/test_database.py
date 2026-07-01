from datetime import UTC, datetime, timedelta

import pytest

from app.database.session import Database
from app.database.tables import Base
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository


@pytest.mark.asyncio
async def test_session_lifecycle(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await database.connect()
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    users = UserRepository(database)
    sessions = SessionRepository(database)
    await users.ensure(1, "Europe/Istanbul")

    start = datetime.now(UTC).replace(microsecond=0)
    work_session = await sessions.start(1, start)
    await sessions.start_break(1, start + timedelta(hours=2))
    await sessions.finish_break(1, start + timedelta(hours=2, minutes=30))
    finished = await sessions.finish(1, start + timedelta(hours=9))

    assert finished.id == work_session.id
    assert len(finished.breaks) == 1
    await sessions.soft_delete(1, work_session.id)
    assert await sessions.get(1, work_session.id) is None
    restored = await sessions.restore(1, work_session.id)
    assert restored.deleted_at_utc is None

    await database.close()
