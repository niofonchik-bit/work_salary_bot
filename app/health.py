from __future__ import annotations

from aiohttp import web

from app.database.session import Database


class HealthServer:
    def __init__(self, database: Database, host: str, port: int):
        self.database = database
        self.host = host
        self.port = port
        self.runner: web.AppRunner | None = None

    async def start(self) -> None:
        # сервер состояния
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/", self._root)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

    async def close(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _health(self, _: web.Request) -> web.Response:
        database_ok = await self.database.ping()
        status = 200 if database_ok else 503
        payload = {"status": "ok" if database_ok else "error", "database": database_ok}
        return web.json_response(payload, status=status)

    async def _root(self, _: web.Request) -> web.Response:
        return web.json_response({"service": "work-salary-bot", "status": "running"})
