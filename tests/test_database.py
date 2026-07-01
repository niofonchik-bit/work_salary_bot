from datetime import UTC, datetime, timedelta

import pytest

from app.database.database import Database


@pytest.mark.asyncio
async def test_database_creates_and_closes_session(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    try:
        await db.ensure_user(123, "Europe/Istanbul")
        start = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
        created = await db.start_session(123, start)
        assert created.ended_at_utc is None
        assert (await db.get_active_session(123)).id == created.id

        ended = await db.end_session(created.id, start + timedelta(hours=9))
        assert ended.ended_at_utc == start + timedelta(hours=9)
        assert await db.get_active_session(123) is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_detects_overlapping_manual_sessions(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    try:
        await db.ensure_user(123, "Europe/Istanbul")
        start = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
        end = start + timedelta(hours=8)
        await db.create_session(123, start, end)

        assert await db.has_overlap(
            123,
            start + timedelta(hours=1),
            end + timedelta(hours=1),
        )
        assert not await db.has_overlap(
            123,
            end,
            end + timedelta(hours=2),
        )
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_rejects_break_equal_to_session_duration(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    try:
        await db.ensure_user(123, "Europe/Istanbul")
        start = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
        end = start + timedelta(hours=1)

        with pytest.raises(ValueError):
            await db.create_session(123, start, end, break_minutes=60)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_rejects_shortening_session_below_break(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    try:
        await db.ensure_user(123, "Europe/Istanbul")
        start = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
        session = await db.create_session(
            123,
            start,
            start + timedelta(hours=2),
            break_minutes=30,
        )

        with pytest.raises(ValueError):
            await db.update_session(
                session.id,
                ended_at_utc=start + timedelta(minutes=30),
            )
    finally:
        await db.close()
