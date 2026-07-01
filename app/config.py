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
    default_timezone: str
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add the bot token.")

        raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
        try:
            allowed_user_ids = frozenset(int(value.strip()) for value in raw_ids.split(",") if value.strip())
        except ValueError as error:
            raise RuntimeError("ALLOWED_USER_IDS must contain Telegram IDs separated by commas.") from error

        database_url = normalize_database_url(
            os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db").strip()
        )
        default_timezone = os.getenv("DEFAULT_TIMEZONE", "Europe/Istanbul").strip() or "Europe/Istanbul"
        try:
            ZoneInfo(default_timezone)
        except ZoneInfoNotFoundError as error:
            raise RuntimeError(
                f"DEFAULT_TIMEZONE contains an unknown IANA timezone: {default_timezone}"
            ) from error

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

        return cls(
            bot_token=bot_token,
            database_url=database_url,
            allowed_user_ids=allowed_user_ids,
            default_timezone=default_timezone,
            log_level=log_level,
        )


def normalize_database_url(value: str) -> str:
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

    # asyncpg uses the ``ssl`` parameter instead of libpq's ``sslmode``.
    sslmode = query.pop("sslmode", None)
    if sslmode and "ssl" not in query:
        query["ssl"] = "require" if sslmode in {"require", "verify-ca", "verify-full"} else sslmode

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
