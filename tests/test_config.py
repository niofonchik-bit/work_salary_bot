from app.config import normalize_database_url


def test_normalize_railway_postgresql_url():
    value = normalize_database_url("postgresql://user:password@postgres.railway.internal:5432/railway")

    assert value == ("postgresql+asyncpg://user:password@postgres.railway.internal:5432/railway")


def test_normalize_legacy_postgres_url():
    value = normalize_database_url("postgres://user:password@host:5432/database")

    assert value == "postgresql+asyncpg://user:password@host:5432/database"


def test_normalize_postgresql_sslmode_for_asyncpg():
    value = normalize_database_url("postgresql://user:password@host:5432/database?sslmode=require")

    assert value == ("postgresql+asyncpg://user:password@host:5432/database?ssl=require")


def test_normalize_plain_sqlite_url():
    value = normalize_database_url("sqlite:///data/bot.db")

    assert value == "sqlite+aiosqlite:///data/bot.db"
