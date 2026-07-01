from app.config import normalize_database_url


def test_postgres_url_normalization() -> None:
    result = normalize_database_url("postgresql://user:pass@host/db?sslmode=require")
    assert result.startswith("postgresql+asyncpg://")
    assert "ssl=require" in result
    assert "sslmode" not in result
