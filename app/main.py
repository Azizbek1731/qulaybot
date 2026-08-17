"""Botni ishga tushirish nuqtasi."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from . import handlers
from .analyzer import Analyzer
from .config import Config, load_config
from .db import Database
from .gemini import GeminiClient
from .middleware import UserMiddleware
from .scheduler import ReminderScheduler

log = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="start", description="Boshlash / ro'yxatdan o'tish"),
    BotCommand(command="tasks", description="Barcha vazifalar"),
    BotCommand(command="today", description="Bugungi ishlar"),
    BotCommand(command="new", description="Qo'lda yangi vazifa"),
    BotCommand(command="ideas", description="💡 Muammo va yechim"),
    BotCommand(command="stats", description="Statistika"),
    BotCommand(command="settings", description="Sozlamalar"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="admin", description="Adminga yozish"),
    BotCommand(command="cancel", description="Amalni bekor qilish"),
]


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def run(config: Config) -> None:
    db = Database(config.db_path)
    await db.connect()

    gemini = GeminiClient(
        config.gemini_api_key,
        text_models=config.gemini_text_models,
        voice_models=config.gemini_voice_models,
    )
    analyzer = Analyzer(gemini)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )

    dp = Dispatcher(storage=MemoryStorage(), db=db, analyzer=analyzer, config=config)

    middleware = UserMiddleware(db, config.default_tz)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_routers(*handlers.ROUTERS)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("Handler xatoligi: %s", event.exception)
        return True

    scheduler = ReminderScheduler(bot, db, config.tick_seconds)

    try:
        me = await bot.get_me()
        log.info("Bot ishga tushdi: @%s (id=%s)", me.username, me.id)

        await bot.set_my_commands(COMMANDS)
        await bot.delete_webhook(drop_pending_updates=False)

        scheduler.start()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        log.info("To'xtatilmoqda...")
        await scheduler.stop()
        await gemini.close()
        await db.close()
        await bot.session.close()


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)
    try:
        asyncio.run(run(config))
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi")


if __name__ == "__main__":
    main()
