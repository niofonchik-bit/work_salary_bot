from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select

from app.config import Config
from app.context import AppContext
from app.database.session import Database
from app.database.tables import AuditEventTable, Base, WorkSessionTable
from app.health import HealthServer


@pytest.mark.asyncio
async def test_geofence_creates_only_one_arrival_per_day(tmp_path) -> None:
    database = await _database(tmp_path / "geofence.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    bot = AsyncMock()
    now = datetime(2026, 7, 1, 6, 4, tzinfo=UTC)
    health = HealthServer(database, bot, context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office", "client": "test"},
        )
        payload = await response.json()
        assert response.status == 201
        assert payload["status"] == "created"
        assert payload["startedAtLocal"].startswith("2026-07-01T09:04:00")
        assert payload["notificationSent"] is True

        async with database.sessions()() as session:
            audit = await session.scalar(
                select(AuditEventTable)
                .where(
                    AuditEventTable.user_id == 123,
                    AuditEventTable.entity_type == "work_session",
                    AuditEventTable.action == "start",
                )
                .order_by(AuditEventTable.id.desc())
            )
        assert audit is not None
        assert audit.after_data["source"] == "geofence"

        repeated = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        assert repeated.status == 200
        assert await repeated.json() == {"status": "ignored", "reason": "active_session_exists"}

        await context.work_time.finish(123, now.replace(hour=15))
        same_day = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        assert same_day.status == 200
        assert await same_day.json() == {
            "status": "ignored",
            "reason": "arrival_already_recorded",
        }

    bot.send_message.assert_awaited_once()
    await database.close()


@pytest.mark.asyncio
async def test_geofence_rejects_invalid_token(tmp_path) -> None:
    database = await _database(tmp_path / "unauthorized.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    health = HealthServer(database, AsyncMock(), context, config, "127.0.0.1", 0)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": "Bearer wrong"},
            json={"zone": "office"},
        )
        assert response.status == 401
        assert await response.json() == {"status": "error", "code": "unauthorized"}

    assert await context.sessions.get_active(123) is None
    await database.close()


@pytest.mark.asyncio
async def test_geofence_endpoint_is_absent_when_disabled(tmp_path) -> None:
    database = await _database(tmp_path / "disabled.db")
    config = _config(database.url, enabled=False)
    context = AppContext.build(config, database)
    health = HealthServer(database, AsyncMock(), context, config, "127.0.0.1", 0)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post("/api/geofence/arrival", json={"zone": "office"})
        assert response.status == 404

    await database.close()


@pytest.mark.asyncio
async def test_geofence_ignores_request_outside_window(tmp_path) -> None:
    database = await _database(tmp_path / "window.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    now = datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
    health = HealthServer(database, AsyncMock(), context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        assert response.status == 200
        assert await response.json() == {
            "status": "ignored",
            "reason": "outside_arrival_window",
        }

    await database.close()


@pytest.mark.asyncio
async def test_geofence_concurrent_requests_create_one_session(tmp_path) -> None:
    database = await _database(tmp_path / "concurrent.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    bot = AsyncMock()
    now = datetime(2026, 7, 1, 6, 4, tzinfo=UTC)
    health = HealthServer(database, bot, context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:

        async def send_request():
            return await client.post(
                "/api/geofence/arrival",
                headers={"Authorization": f"Bearer {config.geofence_secret}"},
                json={"zone": "office"},
            )

        first, second = await asyncio.gather(send_request(), send_request())
        assert sorted([first.status, second.status]) == [200, 201]

    async with database.sessions()() as session:
        count = await session.scalar(select(func.count()).select_from(WorkSessionTable))
    assert count == 1
    bot.send_message.assert_awaited_once()
    await database.close()


@pytest.mark.asyncio
async def test_geofence_notification_error_does_not_rollback_session(tmp_path) -> None:
    database = await _database(tmp_path / "notification.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramNetworkError(
        SendMessage(chat_id=123, text="test"),
        "network unavailable",
    )
    now = datetime(2026, 7, 1, 6, 4, tzinfo=UTC)
    health = HealthServer(database, bot, context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        payload = await response.json()
        assert response.status == 201
        assert payload["notificationSent"] is False

    assert await context.sessions.get_active(123) is not None
    await database.close()


@pytest.mark.asyncio
async def test_previous_night_session_does_not_block_new_day(tmp_path) -> None:
    database = await _database(tmp_path / "night.db")
    config = _config(database.url)
    context = AppContext.build(config, database)
    await context.users.ensure(123, "Europe/Istanbul")
    await context.sessions.add_manual(
        123,
        datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
        datetime(2026, 7, 2, 2, 0, tzinfo=UTC),
    )
    now = datetime(2026, 7, 2, 6, 0, tzinfo=UTC)
    health = HealthServer(database, AsyncMock(), context, config, "127.0.0.1", 0, lambda: now)

    async with TestClient(TestServer(health.build_app())) as client:
        response = await client.post(
            "/api/geofence/arrival",
            headers={"Authorization": f"Bearer {config.geofence_secret}"},
            json={"zone": "office"},
        )
        assert response.status == 201

    await database.close()


async def _database(path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{path}")
    await database.connect()
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return database


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
    )
