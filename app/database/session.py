from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class Database:
    def __init__(self, url: str):
        self.url = url
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        # подключение базы
        parsed_url = make_url(self.url)
        is_sqlite = parsed_url.get_backend_name() == "sqlite"
        if is_sqlite and parsed_url.database and parsed_url.database != ":memory:":
            Path(parsed_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

        engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if is_sqlite:
            engine_kwargs["connect_args"] = {"timeout": 30}

        self.engine = create_async_engine(self.url, **engine_kwargs)
        if is_sqlite:
            _configure_sqlite(self.engine)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def sessions(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("База данных не подключена.")
        return self.session_factory

    async def ping(self) -> bool:
        if self.session_factory is None:
            return False
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def _configure_sqlite(engine: AsyncEngine) -> None:
    # конфигурация sqlite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
