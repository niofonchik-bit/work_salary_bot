from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select

from app.config import Config
from app.context import AppContext
from app.database.enums import PendingShiftStatus
from app.database.session import Database
from app.database.tables import Base, GeofenceEventTable, PendingShiftTable, WorkSessionTable
from app.health import HealthServer


@pytest.mark.asyncio
async def test_geofence_builds_pending_shift_without_session(tmp_path) -> None:
    database = await _database(tmp_path / "geofence.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    bot = _bot()
    current = {"value": datetime(2026, 7, 1, 6, 4, tzinfo=UTC)}
    health = HealthServer(
        database,
        bot,
        context,
        config,
        "127.0.0.1",
        0,
        lambda: current["value"],
    )

    async with TestClient(TestServer(health.build_app())) as client:
        arrival = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office", "client": "test"},
        )
        arrival_payload = await arrival.json()
        assert arrival.status == 202
        assert arrival_payload["status"] == "accepted"
        assert arrival_payload["eventType"] == "arrival"

        assert await _count(database, WorkSessionTable) == 0
        pending = await context.geofence_repository.get(123, arrival_payload["pendingShiftId"])
        assert pending.status == PendingShiftStatus.WAITING_DEPARTURE
        assert pending.suggested_start_utc == current["value"]
        assert pending.suggested_end_utc is None

        current["value"] = datetime(2026, 7, 1, 14, 24, tzinfo=UTC)
        departure = await client.post(
            "/api/geofence/departure",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office", "client": "test"},
        )
        departure_payload = await departure.json()
        assert departure.status == 202
        assert departure_payload["pendingShiftId"] == pending.id

    pending = await context.geofence_repository.get(123, pending.id)
    assert pending.status == PendingShiftStatus.READY
    assert pending.suggested_end_utc == current["value"]
    assert await _count(database, GeofenceEventTable) == 2
    assert await _count(database, PendingShiftTable) == 1
    assert await _count(database, WorkSessionTable) == 0
    bot.send_message.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()
    await database.close()


@pytest.mark.asyncio
async def test_pending_shift_creates_session_only_after_confirmation(tmp_path) -> None:
    database = await _database(tmp_path / "confirm.db")
    context = AppContext.build(_config(database.url), database)
    await context.users.ensure(123, "Europe/Istanbul")

    arrival = await context.geofence.register_event(
        123,
        datetime(2026, 7, 1, tzinfo=UTC).date(),
        "office",
        "arrival",
        datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
        "test",
        15,
    )
    await context.geofence.register_event(
        123,
        datetime(2026, 7, 1, tzinfo=UTC).date(),
        "office",
        "departure",
        datetime(2026, 7, 1, 14, 0, tzinfo=UTC),
        "test",
        15,
    )

    assert await _count(database, WorkSessionTable) == 0
    pending, session = await context.geofence.confirm(123, arrival.pending_shift.id)
    assert pending.status == PendingShiftStatus.CONFIRMED
    assert pending.work_session_id == session.id
    assert session.started_at_utc == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    assert session.ended_at_utc == datetime(2026, 7, 1, 14, 0, tzinfo=UTC)
    assert await _count(database, WorkSessionTable) == 1
    await database.close()


@pytest.mark.asyncio
async def test_all_ready_pending_shifts_can_be_confirmed_together(tmp_path) -> None:
    database = await _database(tmp_path / "bulk.db")
    context = AppContext.build(_config(database.url), database)
    await context.users.ensure(123, "Europe/Istanbul")

    for day in (1, 2):
        local_date = datetime(2026, 7, day, tzinfo=UTC).date()
        await context.geofence.register_event(
            123,
            local_date,
            "office",
            "arrival",
            datetime(2026, 7, day, 6, 0, tzinfo=UTC),
            "test",
            15,
        )
        await context.geofence.register_event(
            123,
            local_date,
            "office",
            "departure",
            datetime(2026, 7, day, 14, 0, tzinfo=UTC),
            "test",
            15,
        )

    confirmed, failed = await context.geofence.confirm_all_ready(123)

    assert len(confirmed) == 2
    assert failed == []
    assert await _count(database, WorkSessionTable) == 2
    assert await context.geofence_repository.list_pending(123) == []
    await database.close()


@pytest.mark.asyncio
async def test_departure_without_arrival_creates_incomplete_shift(tmp_path) -> None:
    database = await _database(tmp_path / "departure.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    now = datetime(2026, 7, 1, 14, 0, tzinfo=UTC)
    health = HealthServer(database, _bot(), context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/event",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office", "event": "departure", "client": "test"},
        )
        payload = await response.json()
        assert response.status == 202

    pending = await context.geofence_repository.get(123, payload["pendingShiftId"])
    assert pending.status == PendingShiftStatus.WAITING_ARRIVAL
    assert pending.suggested_start_utc is None
    assert pending.suggested_end_utc == now
    await database.close()


@pytest.mark.asyncio
async def test_repeated_arrival_is_duplicate_and_keeps_first_time(tmp_path) -> None:
    database = await _database(tmp_path / "duplicate.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    current = {"value": datetime(2026, 7, 1, 6, 0, tzinfo=UTC)}
    health = HealthServer(
        database,
        _bot(),
        context,
        config,
        "127.0.0.1",
        0,
        lambda: current["value"],
    )

    async with TestClient(TestServer(health.build_app())) as client:
        first = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        first_payload = await first.json()
        current["value"] = datetime(2026, 7, 1, 6, 5, tzinfo=UTC)
        second = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        second_payload = await second.json()

    assert first.status == 202
    assert second.status == 200
    assert second_payload["status"] == "duplicate"
    pending = await context.geofence_repository.get(123, first_payload["pendingShiftId"])
    assert pending.suggested_start_utc == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    assert await _count(database, PendingShiftTable) == 1
    assert await _count(database, GeofenceEventTable) == 2
    await database.close()


@pytest.mark.asyncio
async def test_geofence_notification_error_keeps_pending_shift(tmp_path) -> None:
    database = await _database(tmp_path / "notification.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    bot = _bot()
    bot.send_message.side_effect = TelegramNetworkError(
        SendMessage(chat_id=123, text="test"),
        "network unavailable",
    )
    health = HealthServer(
        database,
        bot,
        context,
        config,
        "127.0.0.1",
        0,
        lambda: datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
    )

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        payload = await response.json()
        assert response.status == 202
        assert payload["messageUpdated"] is False

    assert await _count(database, PendingShiftTable) == 1
    assert await _count(database, WorkSessionTable) == 0
    await database.close()


@pytest.mark.asyncio
async def test_geofence_rejects_invalid_token(tmp_path) -> None:
    database = await _database(tmp_path / "unauthorized.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    health = HealthServer(database, _bot(), context, config, "127.0.0.1", 0)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": "Bearer wrong"},
            json={"zone": "office"},
        )
        assert response.status == 401
        assert await response.json() == {"status": "error", "code": "unauthorized"}

    assert await _count(database, PendingShiftTable) == 0
    await database.close()


@pytest.mark.asyncio
async def test_geofence_endpoint_is_absent_when_disabled(tmp_path) -> None:
    database = await _database(tmp_path / "disabled.db")
    config = _config(database.url, enabled=False)
    context = AppContext.build(config, database)
    health = HealthServer(database, _bot(), context, config, "127.0.0.1", 0)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post("/api/geofence/event", json={"zone": "office"})
        assert response.status == 404

    await database.close()


@pytest.mark.asyncio
async def test_geofence_ignores_request_outside_window(tmp_path) -> None:
    database = await _database(tmp_path / "window.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    now = datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
    health = HealthServer(database, _bot(), context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        assert response.status == 200
        assert await response.json() == {
            "status": "ignored",
            "eventType": "arrival",
            "reason": "outside_event_window",
        }

    await database.close()


async def _database(path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{path}")
    await database.connect()
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return database


async def _count(database: Database, table) -> int:
    async with database.sessions()() as session:
        return int(await session.scalar(select(func.count()).select_from(table)) or 0)


def _bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(
        chat=SimpleNamespace(id=123),
        message_id=900,
    )
    return bot


def _config(database_url: str, enabled: bool = True) -> Config:
    return Config(
        bot_token="123:test",
        database_url=database_url,
        allowed_user_ids=frozenset({123}),
        admin_user_id=123,
        default_timezone="Europe/Istanbul",
        log_level="INFO",
        healthcheck_enabled=True,
        healthcheck_host="127.0.0.1",
        healthcheck_port=0,
        reminder_poll_seconds=30,
        is_railway=False,
        geofence_enabled=enabled,
        geofence_secret="a" * 32,
        geofence_user_id=123 if enabled else None,
        geofence_zone="office",
        geofence_arrival_start=time(5, 0),
        geofence_arrival_end=time(13, 0),
        geofence_departure_start=time(12, 0),
        geofence_departure_end=time(23, 59),
        geofence_event_dedup_minutes=15,
    )


@pytest.mark.asyncio
async def test_departure_links_manual_active_session(tmp_path) -> None:
    database = await _database(tmp_path / "manual-arrival.db")
    config = _config(database.url)
    context = AppContext.build(config, database)

    await context.users.ensure(123, "Europe/Istanbul")

    started_at = datetime(
        2026,
        7,
        1,
        6,
        0,
        tzinfo=UTC,
    )
    ended_at = datetime(
        2026,
        7,
        1,
        14,
        20,
        tzinfo=UTC,
    )

    manual_session = await context.work_time.start(
        123,
        started_at,
        source="telegram",
    )

    health = HealthServer(
        database,
        _bot(),
        context,
        config,
        "127.0.0.1",
        0,
        lambda: ended_at,
    )

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/departure",
            headers={"Authorization": (f"Bearer {config.geofence_secret}")},
            json={
                "zone": "office",
                "client": "test",
            },
        )

        payload = await response.json()

        assert response.status == 202

    pending = await context.geofence_repository.get(
        123,
        payload["pendingShiftId"],
    )

    assert pending.status == PendingShiftStatus.READY
    assert pending.work_session_id == manual_session.id
    assert pending.suggested_start_utc == started_at
    assert pending.suggested_end_utc == ended_at

    confirmed, finished_session = await context.geofence.confirm(
        123,
        pending.id,
    )

    assert confirmed.status == PendingShiftStatus.CONFIRMED
    assert finished_session.id == manual_session.id
    assert finished_session.started_at_utc == started_at
    assert finished_session.ended_at_utc == ended_at
    assert await _count(database, WorkSessionTable) == 1

    await database.close()


@pytest.mark.asyncio
async def test_new_event_after_rejected_shift_creates_new_pending_shift(
    tmp_path,
) -> None:
    database = await _database(tmp_path / "rejected-retry.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")

    bot = _bot()
    current = {
        "value": datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
    }

    health = HealthServer(
        database,
        bot,
        context,
        config,
        "127.0.0.1",
        0,
        lambda: current["value"],
    )

    async with TestClient(TestServer(health.build_app())) as client:
        first_response = await client.post(
            "/api/geofence/arrival",
            headers={
                "Authorization": f"Bearer {config.geofence_secret}",
            },
            json={
                "zone": "office",
                "client": "test",
            },
        )

        first_payload = await first_response.json()
        first_id = first_payload["pendingShiftId"]

        rejected = await context.geofence.reject(123, first_id)

        assert rejected.status == PendingShiftStatus.REJECTED

        current["value"] = datetime(
            2026,
            7,
            1,
            6,
            30,
            tzinfo=UTC,
        )

        second_response = await client.post(
            "/api/geofence/arrival",
            headers={
                "Authorization": f"Bearer {config.geofence_secret}",
            },
            json={
                "zone": "office",
                "client": "test",
            },
        )

        second_payload = await second_response.json()

    assert first_response.status == 202
    assert second_response.status == 202
    assert second_payload["status"] == "accepted"
    assert second_payload["pendingShiftId"] != first_id

    first_pending = await context.geofence_repository.get(
        123,
        first_id,
    )
    second_pending = await context.geofence_repository.get(
        123,
        second_payload["pendingShiftId"],
    )

    assert first_pending.status == PendingShiftStatus.REJECTED
    assert second_pending.status == PendingShiftStatus.WAITING_DEPARTURE

    assert await _count(database, PendingShiftTable) == 2
    assert await _count(database, GeofenceEventTable) == 2
    assert bot.send_message.await_count == 2

    await database.close()


@pytest.mark.asyncio
async def test_duplicate_event_does_not_repeat_notification(
    tmp_path,
) -> None:
    database = await _database(tmp_path / "duplicate-notification.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")

    bot = _bot()
    current = {
        "value": datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
    }

    health = HealthServer(
        database,
        bot,
        context,
        config,
        "127.0.0.1",
        0,
        lambda: current["value"],
    )

    async with TestClient(TestServer(health.build_app())) as client:
        await client.post(
            "/api/geofence/arrival",
            headers={
                "Authorization": f"Bearer {config.geofence_secret}",
            },
            json={"zone": "office"},
        )

        current["value"] = datetime(
            2026,
            7,
            1,
            6,
            5,
            tzinfo=UTC,
        )

        duplicate_response = await client.post(
            "/api/geofence/arrival",
            headers={
                "Authorization": f"Bearer {config.geofence_secret}",
            },
            json={"zone": "office"},
        )

        duplicate_payload = await duplicate_response.json()

    assert duplicate_response.status == 200
    assert duplicate_payload["status"] == "duplicate"
    assert duplicate_payload["messageUpdated"] is False

    assert bot.send_message.await_count == 1
    bot.edit_message_text.assert_not_awaited()

    await database.close()
