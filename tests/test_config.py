from __future__ import annotations

from datetime import time

import pytest

from app.config import Config, normalize_database_url


def test_postgres_url_normalization() -> None:
    result = normalize_database_url("postgresql://user:pass@host/db?sslmode=require")
    assert result.startswith("postgresql+asyncpg://")
    assert "ssl=require" in result
    assert "sslmode" not in result


def test_disabled_geofence_does_not_require_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_environment(monkeypatch)
    monkeypatch.setenv("GEOFENCE_ENABLED", "false")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_START", "")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_END", "")

    config = Config.from_env()

    assert config.geofence_enabled is False
    assert config.geofence_user_id is None


def test_enabled_geofence_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_environment(monkeypatch)
    monkeypatch.setenv("GEOFENCE_ENABLED", "true")
    monkeypatch.setenv("GEOFENCE_SECRET", "a" * 32)
    monkeypatch.setenv("GEOFENCE_USER_ID", "123")
    monkeypatch.setenv("GEOFENCE_ZONE", "office")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_START", "05:00")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_END", "13:00")

    config = Config.from_env()

    assert config.geofence_enabled is True
    assert config.geofence_user_id == 123
    assert config.geofence_zone == "office"
    assert config.geofence_arrival_start == time(5, 0)
    assert config.geofence_arrival_end == time(13, 0)
    assert config.geofence_departure_start == time(12, 0)
    assert config.geofence_departure_end == time(23, 59)
    assert config.geofence_event_dedup_minutes == 15


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("GEOFENCE_SECRET", "short", "не менее 32"),
        ("GEOFENCE_USER_ID", "0", "положительным"),
        ("GEOFENCE_ZONE", "", "от 1 до 64"),
        ("GEOFENCE_ARRIVAL_START", "13:00", "завершаться позже"),
    ],
)
def test_invalid_geofence_configuration(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    _base_environment(monkeypatch)
    monkeypatch.setenv("GEOFENCE_ENABLED", "true")
    monkeypatch.setenv("GEOFENCE_SECRET", "a" * 32)
    monkeypatch.setenv("GEOFENCE_USER_ID", "123")
    monkeypatch.setenv("GEOFENCE_ZONE", "office")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_START", "05:00")
    monkeypatch.setenv("GEOFENCE_ARRIVAL_END", "13:00")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        Config.from_env()


def test_geofence_user_must_be_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_environment(monkeypatch)
    monkeypatch.setenv("GEOFENCE_ENABLED", "true")
    monkeypatch.setenv("GEOFENCE_SECRET", "a" * 32)
    monkeypatch.setenv("GEOFENCE_USER_ID", "456")

    with pytest.raises(RuntimeError, match="ALLOWED_USER_IDS"):
        Config.from_env()


def _base_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:test")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "Europe/Istanbul")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("GEOFENCE_SECRET", raising=False)
    monkeypatch.delenv("GEOFENCE_USER_ID", raising=False)
    monkeypatch.delenv("GEOFENCE_ZONE", raising=False)
    monkeypatch.delenv("GEOFENCE_ARRIVAL_START", raising=False)
    monkeypatch.delenv("GEOFENCE_ARRIVAL_END", raising=False)
    monkeypatch.delenv("GEOFENCE_DEPARTURE_START", raising=False)
    monkeypatch.delenv("GEOFENCE_DEPARTURE_END", raising=False)
    monkeypatch.delenv("GEOFENCE_EVENT_DEDUP_MINUTES", raising=False)
