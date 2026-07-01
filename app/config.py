from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    database_url: str
    allowed_user_ids: frozenset[int]
    admin_user_id: int | None
    default_timezone: str
    log_level: str
    healthcheck_enabled: bool
    healthcheck_host: str
    healthcheck_port: int
    reminder_poll_seconds: int
    is_railway: bool

    @classmethod
    def from_env(cls) -> Config:
        # конфигурация окружения
        load_dotenv()

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN не задан. Скопируйте .env.example в .env и добавьте токен.")

        allowed_user_ids = _parse_id_set(os.getenv("ALLOWED_USER_IDS", ""))
        is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
        if is_railway and not allowed_user_ids:
            raise RuntimeError("ALLOWED_USER_IDS обязателен для запуска на Railway.")

        admin_user_id = _parse_optional_int(os.getenv("ADMIN_USER_ID", ""), "ADMIN_USER_ID")
        default_timezone = os.getenv("DEFAULT_TIMEZONE", "Europe/Istanbul").strip() or "Europe/Istanbul"
        try:
            ZoneInfo(default_timezone)
        except ZoneInfoNotFoundError as error:
            raise RuntimeError(f"Неизвестный часовой пояс: {default_timezone}") from error

        database_url = normalize_database_url(
            os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db").strip()
        )
        healthcheck_port = int(os.getenv("PORT", "8080"))
        reminder_poll_seconds = max(10, int(os.getenv("REMINDER_POLL_SECONDS", "30")))

        return cls(
            bot_token=bot_token,
            database_url=database_url,
            allowed_user_ids=allowed_user_ids,
            admin_user_id=admin_user_id,
            default_timezone=default_timezone,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            healthcheck_enabled=_parse_bool(os.getenv("HEALTHCHECK_ENABLED", "true")),
            healthcheck_host=os.getenv("HEALTHCHECK_HOST", "0.0.0.0").strip() or "0.0.0.0",
            healthcheck_port=healthcheck_port,
            reminder_poll_seconds=reminder_poll_seconds,
            is_railway=is_railway,
        )


def normalize_database_url(value: str) -> str:
    # нормализация адреса базы
    url = value or "sqlite+aiosqlite:///data/bot.db"
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    elif url.startswith("sqlite:///"):
        url = "sqlite+aiosqlite:///" + url.removeprefix("sqlite:///")

    if not url.startswith("postgresql+asyncpg://"):
        return url

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    if sslmode and "ssl" not in query:
        query["ssl"] = "require" if sslmode in {"require", "verify-ca", "verify-full"} else sslmode
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _parse_id_set(value: str) -> frozenset[int]:
    try:
        return frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise RuntimeError("ALLOWED_USER_IDS должен содержать Telegram ID через запятую.") from error


def _parse_optional_int(value: str, name: str) -> int | None:
    if not value.strip():
        return None
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} должен быть целым числом.") from error


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
