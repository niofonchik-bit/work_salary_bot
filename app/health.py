from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiohttp import web
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config
from app.context import AppContext
from app.database.enums import GeofenceEventStatus
from app.database.session import Database
from app.services.geofence_notifications import sync_pending_notification

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
            app.router.add_post("/api/geofence/event", self._geofence_event)
            app.router.add_post("/api/geofence/arrival", self._geofence_arrival)
            app.router.add_post("/api/geofence/departure", self._geofence_departure)
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
        return await self._handle_geofence_event(request, "arrival")

    async def _geofence_departure(self, request: web.Request) -> web.Response:
        return await self._handle_geofence_event(request, "departure")

    async def _geofence_event(self, request: web.Request) -> web.Response:
        return await self._handle_geofence_event(request, None)

    async def _handle_geofence_event(
        self,
        request: web.Request,
        forced_event_type: str | None,
    ) -> web.Response:
        # обработчик геозоны
        if not self._authorized(request):
            logger.warning(
                "Geofence authorization failed",
                extra={"event": "geofence_event_unauthorized"},
            )
            return _error_response("unauthorized", 401)

        payload = await self._read_payload(request, forced_event_type)
        if payload is None:
            return _error_response("invalid_request", 400)

        zone = payload["zone"]
        event_type = payload["event"]
        if zone != self.config.geofence_zone:
            return _error_response("invalid_request", 400)

        user_id = self.config.geofence_user_id
        if user_id is None:
            return _error_response("user_not_initialized", 409)

        try:
            user = await self.context.users.get(user_id)
            now_utc = self.now_provider().astimezone(UTC)
            now_local = now_utc.astimezone(ZoneInfo(user.timezone))
            if not self._inside_event_window(event_type, now_local.time()):
                return self._ignored(user_id, zone, event_type, "outside_event_window")

            registration = await self.context.geofence.register_event(
                user_id=user_id,
                local_date=now_local.date(),
                zone=zone,
                event_type=event_type,
                occurred_at_utc=now_utc,
                client=payload["client"],
                dedup_minutes=self.config.geofence_event_dedup_minutes,
            )
            notification_sent = False

            if registration.event.status != GeofenceEventStatus.DUPLICATE:
                notification_sent = await sync_pending_notification(
                    self.bot,
                    self.context.geofence_repository,
                    registration.pending_shift,
                    user.timezone,
                )

            response_status = 200 if registration.duplicate else 202
            logger.info(
                "Geofence event accepted",
                extra={
                    "event": "geofence_event_accepted",
                    "user_id": user_id,
                    "reason": registration.event.status,
                    "zone": zone,
                    "notification_sent": notification_sent,
                },
            )
            return web.json_response(
                {
                    "status": "duplicate" if registration.duplicate else "accepted",
                    "eventId": registration.event.id,
                    "eventType": event_type,
                    "eventStatus": registration.event.status,
                    "pendingShiftId": registration.pending_shift.id,
                    "occurredAtUtc": now_utc.isoformat(),
                    "occurredAtLocal": now_local.isoformat(),
                    "timezone": user.timezone,
                    "messageUpdated": notification_sent,
                },
                status=response_status,
            )
        except LookupError:
            return _error_response("user_not_initialized", 409)
        except SQLAlchemyError:
            logger.exception(
                "Geofence database error",
                extra={"event": "geofence_event_failed", "user_id": user_id},
            )
            return _error_response("database_unavailable", 503)
        except TelegramAPIError:
            logger.exception(
                "Geofence notification error",
                extra={"event": "geofence_notification_failed", "user_id": user_id},
            )
            return _error_response("notification_unavailable", 503)
        except Exception:
            logger.exception(
                "Geofence event error",
                extra={"event": "geofence_event_failed", "user_id": user_id},
            )
            return _error_response("internal_error", 500)

    def _authorized(self, request: web.Request) -> bool:
        # проверка авторизации
        header = request.headers.get("Authorization", "")
        scheme, separator, token = header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            return False
        return hmac.compare_digest(token, self.config.geofence_secret)

    async def _read_payload(
        self,
        request: web.Request,
        forced_event_type: str | None,
    ) -> dict[str, str] | None:
        # тело запроса
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None

        zone = payload.get("zone")
        client = payload.get("client", "")
        event_type = forced_event_type or payload.get("event")
        if not isinstance(zone, str) or not zone or len(zone) > 64:
            return None
        if not isinstance(client, str) or len(client) > 64:
            return None
        if event_type not in {"arrival", "departure"}:
            return None
        return {"zone": zone, "client": client, "event": event_type}

    def _inside_event_window(self, event_type: str, local_time: time) -> bool:
        if event_type == "arrival":
            return self.config.geofence_arrival_start <= local_time < self.config.geofence_arrival_end
        return self.config.geofence_departure_start <= local_time < self.config.geofence_departure_end

    def _ignored(
        self,
        user_id: int,
        zone: str,
        event_type: str,
        reason: str,
    ) -> web.Response:
        logger.info(
            "Geofence event ignored",
            extra={
                "event": "geofence_event_ignored",
                "user_id": user_id,
                "reason": reason,
                "zone": zone,
            },
        )
        return web.json_response(
            {
                "status": "ignored",
                "eventType": event_type,
                "reason": reason,
            }
        )


def _error_response(code: str, status: int) -> web.Response:
    return web.json_response({"status": "error", "code": code}, status=status)
