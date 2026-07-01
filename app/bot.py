from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.engine import make_url

from app.config import Config
from app.database.database import Database
from app.handlers import build_root_router
from app.middlewares.access import AccessMiddleware

logger = logging.getLogger(__name__)


async def run_bot(config: Config) -> None:
    database = Database(config.database_url)
    await _connect_database(database)

    database_backend = make_url(config.database_url).get_backend_name()
    logger.info("Database connected: %s", database_backend)

    bot: Bot | None = None
    try:
        bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher.include_router(build_root_router())

        access_middleware = AccessMiddleware()
        dispatcher.message.outer_middleware(access_middleware)
        dispatcher.callback_query.outer_middleware(access_middleware)

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть главное меню"),
                BotCommand(command="help", description="Справка"),
                BotCommand(command="cancel", description="Отменить текущий ввод"),
                BotCommand(command="myid", description="Показать Telegram ID"),
            ]
        )

        # long polling cannot work while a webhook is active
        await bot.delete_webhook(drop_pending_updates=False)

        logger.info("Bot polling started")
        await dispatcher.start_polling(
            bot,
            config=config,
            db=database,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        logger.info("Bot polling stopped")
        if bot is not None:
            await bot.session.close()
        await database.close()


async def _connect_database(database: Database) -> None:
    max_attempts = 10
    for attempt in range(1, max_attempts + 1):
        try:
            await database.connect()
            return
        except Exception:
            await database.close()
            if attempt == max_attempts:
                raise
            delay = min(2 ** (attempt - 1), 15)
            logger.exception(
                "Database connection failed on attempt %s/%s. Retrying in %s seconds",
                attempt,
                max_attempts,
                delay,
            )
            await asyncio.sleep(delay)


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_bot(config))
