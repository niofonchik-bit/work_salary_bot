import pytest

from app.database.session import Database
from app.database.tables import Base
from app.repositories.fsm import FsmRepository


@pytest.mark.asyncio
async def test_data_update_preserves_state(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'fsm.db'}")
    await database.connect()
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = FsmRepository(database)

    await repository.set_state("key", "form:value")
    await repository.set_data("key", {"value": 10})

    state, data = await repository.get("key")
    assert state == "form:value"
    assert data == {"value": 10}
    await database.close()
