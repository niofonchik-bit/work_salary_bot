from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiohttp import web
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config
from app.context import AppContext
from app.database.session import Database
from app.keyboards.inline import dismiss_keyboard

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(
        self,
        database: Database,
        bot: Bot,
        context: AppContext,
        config: Config,
        host: str,
        port: int,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.database = database
        self.bot = bot
        self.context = context
        self.config = config
        self.host = host
        self.port = port
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.runner: web.AppRunner | None = None

    def build_app(self) -> web.Application:
        # приложение сервера
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/", self._root)
        if self.config.geofence_enabled:
            app.router.add_post("/api/geofence/arrival", self._geofence_arrival)
        return app

    async def start(self) -> None:
        # сервер состояния
        self.runner = web.AppRunner(self.build_app())
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

    async def _geofence_arrival(self, request: web.Request) -> web.Response:
        # обработчик геозоны
        if not self._authorized(request):
            logger.warning("Geofence authorization failed", extra={"event": "geofence_arrival_unauthorized"})
            return _error_response("unauthorized", 401)

        payload = await self._read_payload(request)
        if payload is None:
            return _error_response("invalid_request", 400)

        zone = payload["zone"]
        if zone != self.config.geofence_zone:
            return _error_response("invalid_request", 400)

        user_id = self.config.geofence_user_id
        if user_id is None:
            return _error_response("user_not_initialized", 409)

        try:
            user = await self.context.users.get(user_id)
            now_utc = self.now_provider().astimezone(UTC)
            zone_info = ZoneInfo(user.timezone)
            now_local = now_utc.astimezone(zone_info)

            if not self._inside_arrival_window(now_local.time()):
                return self._ignored(user_id, zone, "outside_arrival_window")

            active = await self.context.sessions.get_active(user_id)
            if active is not None:
                return self._ignored(user_id, zone, "active_session_exists")

            day_start_local = datetime.combine(now_local.date(), time.min, tzinfo=zone_info)
            day_end_local = day_start_local + timedelta(days=1)
            already_recorded = await self.context.sessions.exists_started_between(
                user_id,
                day_start_local.astimezone(UTC),
                day_end_local.astimezone(UTC),
            )
            if already_recorded:
                return self._ignored(user_id, zone, "arrival_already_recorded")

            try:
                work_session = await self.context.work_time.start(
                    user_id,
                    now_utc,
                    source="geofence",
                )
            except ValueError:
                active = await self.context.sessions.get_active(user_id)
                reason = "active_session_exists" if active is not None else "arrival_already_recorded"
                return self._ignored(user_id, zone, reason)

            notification_sent = await self._send_notification(user_id, work_session.id, now_local)
            logger.info(
                "Geofence arrival created",
                extra={
                    "event": "geofence_arrival_created",
                    "user_id": user_id,
                    "session_id": work_session.id,
                    "zone": zone,
                    "notification_sent": notification_sent,
                },
            )
            return web.json_response(
                {
                    "status": "created",
                    "sessionId": work_session.id,
                    "startedAtUtc": now_utc.isoformat(),
                    "startedAtLocal": now_local.isoformat(),
                    "timezone": user.timezone,
                    "notificationSent": notification_sent,
                },
                status=201,
            )
        except LookupError:
            return _error_response("user_not_initialized", 409)
        except SQLAlchemyError:
            logger.exception(
                "Geofence database error",
                extra={"event": "geofence_arrival_failed", "user_id": user_id},
            )
            return _error_response("database_unavailable", 503)
        except Exception:
            logger.exception(
                "Geofence arrival error",
                extra={"event": "geofence_arrival_failed", "user_id": user_id},
            )
            return _error_response("internal_error", 500)

    def _authorized(self, request: web.Request) -> bool:
        # проверка авторизации
        header = request.headers.get("Authorization", "")
        scheme, separator, token = header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            return False
        return hmac.compare_digest(token, self.config.geofence_secret)

    async def _read_payload(self, request: web.Request) -> dict[str, str] | None:
        # тело запроса
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None

        zone = payload.get("zone")
        client = payload.get("client", "")
        if not isinstance(zone, str) or not zone or len(zone) > 64:
            return None
        if not isinstance(client, str) or len(client) > 64:
            return None
        return {"zone": zone, "client": client}

    def _inside_arrival_window(self, local_time: time) -> bool:
        return self.config.geofence_arrival_start <= local_time < self.config.geofence_arrival_end

    def _ignored(self, user_id: int, zone: str, reason: str) -> web.Response:
        logger.info(
            "Geofence arrival ignored",
            extra={
                "event": "geofence_arrival_ignored",
                "user_id": user_id,
                "reason": reason,
                "zone": zone,
            },
        )
        return web.json_response({"status": "ignored", "reason": reason})

    async def _send_notification(self, user_id: int, session_id: int, now_local: datetime) -> bool:
        # уведомление геозоны
        try:
            await self.bot.send_message(
                user_id,
                f"📍 Приход отмечен автоматически: <b>{now_local:%H:%M}</b>\nИсточник: геозона офиса",
                reply_markup=dismiss_keyboard(),
            )
            return True
        except TelegramAPIError:
            logger.exception(
                "Geofence notification failed",
                extra={
                    "event": "geofence_notification_failed",
                    "user_id": user_id,
                    "session_id": session_id,
                },
            )
            return False


def _error_response(code: str, status: int) -> web.Response:
    return web.json_response({"status": "error", "code": code}, status=status)
