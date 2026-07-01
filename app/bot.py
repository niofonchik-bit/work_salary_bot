from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import Config
from app.context import AppContext
from app.database.session import Database
from app.database.storage import DatabaseStorage
from app.handlers import build_root_router
from app.health import HealthServer
from app.logging_config import configure_logging
from app.middlewares.access import AccessMiddleware
from app.repositories.fsm import FsmRepository
from app.services.reminder_engine import ReminderEngine

logger = logging.getLogger(__name__)


async def run_bot(config: Config) -> None:
    # запуск приложения
    database = Database(config.database_url)
    await _connect_database(database)
    context = AppContext.build(config, database)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = DatabaseStorage(FsmRepository(database))
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(build_root_router())

    access = AccessMiddleware(config.allowed_user_ids)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)

    health = HealthServer(
        database,
        bot,
        context,
        config,
        config.healthcheck_host,
        config.healthcheck_port,
    )
    reminder_engine = ReminderEngine(bot, context, config.reminder_poll_seconds)
    reminder_task: asyncio.Task | None = None

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню"),
                BotCommand(command="help", description="Справка"),
                BotCommand(command="cancel", description="Отмена ввода"),
                BotCommand(command="myid", description="Telegram ID"),
                BotCommand(command="status", description="Состояние приложения"),
            ]
        )
        await bot.delete_webhook(drop_pending_updates=False)
        if config.healthcheck_enabled or config.geofence_enabled:
            await health.start()
        reminder_task = asyncio.create_task(reminder_engine.run(), name="reminder-engine")
        logger.info("Bot polling started", extra={"event": "bot_started"})
        await dispatcher.start_polling(
            bot,
            context=context,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        logger.info("Bot polling stopped", extra={"event": "bot_stopped"})
        if reminder_task is not None:
            reminder_task.cancel()
            await asyncio.gather(reminder_task, return_exceptions=True)
        await health.close()
        await storage.close()
        await bot.session.close()
        await database.close()


async def _connect_database(database: Database) -> None:
    # подключение базы
    for attempt in range(1, 11):
        try:
            await database.connect()
            return
        except Exception:
            await database.close()
            if attempt == 10:
                raise
            delay = min(2 ** (attempt - 1), 15)
            logger.exception(
                "Database connection failed",
                extra={"event": "database_connection_failed"},
            )
            await asyncio.sleep(delay)


def main() -> None:
    config = Config.from_env()
    configure_logging(config.log_level)
    asyncio.run(run_bot(config))
