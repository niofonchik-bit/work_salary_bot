from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, event, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.models import MonthlySettings, UserSettings, WorkSession
from app.database.tables import Base, MonthlySettingsTable, UserTable, WorkSessionTable


class Database:
    def __init__(self, url: str | Path):
        if isinstance(url, Path):
            url = f"sqlite+aiosqlite:///{url.as_posix()}"
        self.url = url
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        parsed_url = make_url(self.url)
        is_sqlite = parsed_url.get_backend_name() == "sqlite"

        if is_sqlite and parsed_url.database and parsed_url.database != ":memory:":
            Path(parsed_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
        }
        if is_sqlite:
            engine_kwargs["connect_args"] = {"timeout": 30}

        self.engine = create_async_engine(self.url, **engine_kwargs)

        if is_sqlite:
            _configure_sqlite(self.engine)

        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def _sessions(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("Database is not connected")
        return self.session_factory

    async def ensure_user(self, telegram_id: int, timezone_name: str) -> None:
        now = datetime.now(UTC)
        async with self._sessions()() as session:
            if await session.get(UserTable, telegram_id) is not None:
                return

            session.add(
                UserTable(
                    telegram_id=telegram_id,
                    timezone=timezone_name,
                    created_at_utc=now,
                    updated_at_utc=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def get_user_settings(self, telegram_id: int) -> UserSettings:
        async with self._sessions()() as session:
            row = await session.get(UserTable, telegram_id)
            if row is None:
                raise LookupError(f"User {telegram_id} was not initialized")
            return _to_user_settings(row)

    async def update_user_setting(self, telegram_id: int, field: str, value: Any) -> None:
        allowed_fields = {
            "timezone",
            "workday_minutes",
            "default_salary_cents",
            "default_bonus_cents",
            "default_target_cents",
            "overtime_mode",
            "custom_rate_cents",
            "weekend_multiplier",
        }
        if field not in allowed_fields:
            raise ValueError(f"Unsupported user setting: {field}")

        async with self._sessions()() as session:
            row = await session.get(UserTable, telegram_id)
            if row is None:
                raise LookupError(f"User {telegram_id} was not initialized")
            setattr(row, field, value)
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()

    async def get_month_settings(self, user_id: int, year: int, month: int) -> MonthlySettings:
        key = (user_id, year, month)
        async with self._sessions()() as session:
            row = await session.get(MonthlySettingsTable, key)
            if row is None:
                user = await session.get(UserTable, user_id)
                if user is None:
                    raise LookupError(f"User {user_id} was not initialized")

                row = MonthlySettingsTable(
                    user_id=user_id,
                    year=year,
                    month=month,
                    salary_cents=user.default_salary_cents,
                    bonus_cents=user.default_bonus_cents,
                    target_cents=user.default_target_cents,
                    standard_minutes=None,
                )
                session.add(row)
                try:
                    await session.commit()
                except IntegrityError as error:
                    await session.rollback()
                    row = await session.get(MonthlySettingsTable, key)
                    if row is None:
                        raise RuntimeError("Monthly settings were not created") from error

            return _to_monthly_settings(row)

    async def update_month_setting(
        self,
        user_id: int,
        year: int,
        month: int,
        field: str,
        value: Any,
    ) -> None:
        allowed_fields = {"salary_cents", "bonus_cents", "target_cents", "standard_minutes"}
        if field not in allowed_fields:
            raise ValueError(f"Unsupported monthly setting: {field}")

        await self.get_month_settings(user_id, year, month)
        async with self._sessions()() as session:
            row = await session.get(MonthlySettingsTable, (user_id, year, month))
            if row is None:
                raise LookupError("Monthly settings were not created")
            setattr(row, field, value)
            await session.commit()

    async def get_active_session(self, user_id: int) -> WorkSession | None:
        statement = (
            select(WorkSessionTable)
            .where(
                WorkSessionTable.user_id == user_id,
                WorkSessionTable.ended_at_utc.is_(None),
            )
            .order_by(WorkSessionTable.started_at_utc.desc())
            .limit(1)
        )
        row = await self._first(statement)
        return _to_work_session(row) if row else None

    async def start_session(self, user_id: int, started_at_utc: datetime) -> WorkSession:
        started_at_utc = _require_aware_utc(started_at_utc)
        now = datetime.now(UTC)

        async with self._sessions()() as session:
            row = WorkSessionTable(
                user_id=user_id,
                started_at_utc=started_at_utc,
                ended_at_utc=None,
                break_minutes=0,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ValueError("User already has an active session") from error
            await session.refresh(row)
            return _to_work_session(row)

    async def end_session(self, session_id: int, ended_at_utc: datetime) -> WorkSession:
        ended_at_utc = _require_aware_utc(ended_at_utc)
        async with self._sessions()() as session:
            row = await session.get(WorkSessionTable, session_id)
            if row is None:
                raise LookupError("Session was not found")
            start_utc = _as_utc(row.started_at_utc)
            _validate_session_values(start_utc, ended_at_utc, row.break_minutes)

            row.ended_at_utc = ended_at_utc
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return _to_work_session(row)

    async def create_session(
        self,
        user_id: int,
        started_at_utc: datetime,
        ended_at_utc: datetime,
        break_minutes: int = 0,
    ) -> WorkSession:
        started_at_utc = _require_aware_utc(started_at_utc)
        ended_at_utc = _require_aware_utc(ended_at_utc)
        _validate_session_values(started_at_utc, ended_at_utc, break_minutes)

        now = datetime.now(UTC)
        async with self._sessions()() as session:
            row = WorkSessionTable(
                user_id=user_id,
                started_at_utc=started_at_utc,
                ended_at_utc=ended_at_utc,
                break_minutes=break_minutes,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_work_session(row)

    async def get_session(self, session_id: int) -> WorkSession | None:
        async with self._sessions()() as session:
            row = await session.get(WorkSessionTable, session_id)
            return _to_work_session(row) if row else None

    async def list_sessions(
        self,
        user_id: int,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[WorkSession]:
        start_utc = _require_aware_utc(start_utc)
        end_utc = _require_aware_utc(end_utc)
        statement = (
            select(WorkSessionTable)
            .where(
                WorkSessionTable.user_id == user_id,
                WorkSessionTable.started_at_utc < end_utc,
                or_(
                    WorkSessionTable.ended_at_utc.is_(None),
                    WorkSessionTable.ended_at_utc > start_utc,
                ),
            )
            .order_by(WorkSessionTable.started_at_utc.asc())
        )
        async with self._sessions()() as session:
            rows = (await session.scalars(statement)).all()
            return [_to_work_session(row) for row in rows]

    async def has_overlap(
        self,
        user_id: int,
        started_at_utc: datetime,
        ended_at_utc: datetime | None,
        exclude_session_id: int | None = None,
    ) -> bool:
        started_at_utc = _require_aware_utc(started_at_utc)
        end_boundary = (
            _require_aware_utc(ended_at_utc) if ended_at_utc is not None else datetime.max.replace(tzinfo=UTC)
        )
        statement = select(WorkSessionTable.id).where(
            WorkSessionTable.user_id == user_id,
            WorkSessionTable.started_at_utc < end_boundary,
            or_(
                WorkSessionTable.ended_at_utc.is_(None),
                WorkSessionTable.ended_at_utc > started_at_utc,
            ),
        )
        if exclude_session_id is not None:
            statement = statement.where(WorkSessionTable.id != exclude_session_id)
        statement = statement.limit(1)

        async with self._sessions()() as session:
            return await session.scalar(statement) is not None

    async def update_session(
        self,
        session_id: int,
        *,
        started_at_utc: datetime | None = None,
        ended_at_utc: datetime | None = None,
        break_minutes: int | None = None,
    ) -> WorkSession:
        async with self._sessions()() as session:
            row = await session.get(WorkSessionTable, session_id)
            if row is None:
                raise LookupError("Session not found")

            new_start = (
                _require_aware_utc(started_at_utc)
                if started_at_utc is not None
                else _as_utc(row.started_at_utc)
            )
            new_end = (
                _require_aware_utc(ended_at_utc)
                if ended_at_utc is not None
                else (_as_utc(row.ended_at_utc) if row.ended_at_utc else None)
            )
            new_break = break_minutes if break_minutes is not None else row.break_minutes

            _validate_session_values(new_start, new_end, new_break)

            row.started_at_utc = new_start
            row.ended_at_utc = new_end
            row.break_minutes = new_break
            row.updated_at_utc = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return _to_work_session(row)

    async def delete_session(self, session_id: int) -> None:
        async with self._sessions()() as session:
            row = await session.get(WorkSessionTable, session_id)
            if row is None:
                return
            await session.delete(row)
            await session.commit()

    async def _first(self, statement: Select[tuple[WorkSessionTable]]) -> WorkSessionTable | None:
        async with self._sessions()() as session:
            return await session.scalar(statement)


def _configure_sqlite(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()


def _validate_session_values(
    started_at_utc: datetime,
    ended_at_utc: datetime | None,
    break_minutes: int,
) -> None:
    if break_minutes < 0:
        raise ValueError("Break cannot be negative")
    if ended_at_utc is None:
        return
    if ended_at_utc <= started_at_utc:
        raise ValueError("Session end must be after start")

    duration_minutes = int((ended_at_utc - started_at_utc).total_seconds() / 60)
    if break_minutes >= duration_minutes:
        raise ValueError("Break must be shorter than the session")


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime is required")
    return value.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_user_settings(row: UserTable) -> UserSettings:
    return UserSettings(
        telegram_id=row.telegram_id,
        timezone=row.timezone,
        workday_minutes=row.workday_minutes,
        default_salary_cents=row.default_salary_cents,
        default_bonus_cents=row.default_bonus_cents,
        default_target_cents=row.default_target_cents,
        overtime_mode=row.overtime_mode,
        custom_rate_cents=row.custom_rate_cents,
        weekend_multiplier=row.weekend_multiplier,
    )


def _to_monthly_settings(row: MonthlySettingsTable) -> MonthlySettings:
    return MonthlySettings(
        user_id=row.user_id,
        year=row.year,
        month=row.month,
        salary_cents=row.salary_cents,
        bonus_cents=row.bonus_cents,
        target_cents=row.target_cents,
        standard_minutes=row.standard_minutes,
    )


def _to_work_session(row: WorkSessionTable) -> WorkSession:
    return WorkSession(
        id=row.id,
        user_id=row.user_id,
        started_at_utc=_as_utc(row.started_at_utc),
        ended_at_utc=_as_utc(row.ended_at_utc) if row.ended_at_utc else None,
        break_minutes=row.break_minutes,
        created_at_utc=_as_utc(row.created_at_utc),
        updated_at_utc=_as_utc(row.updated_at_utc),
    )
