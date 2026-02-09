"""
TG Hub — Telegram бот YouHub. Точка входа: только запуск и wiring.

Вся бизнес-логика: tg_hub_bot (handlers, services), storage, services.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, WEBAPP_HUB_URL
from storage.bootstrap import get_tasks_repo
from services.ai_service import create_ai_service
from services.scheduler_service import create_scheduler, start_scheduler
from tg_hub_bot.handlers.start import register_start_handler
from tg_hub_bot.handlers.ai_chat import register_ai_chat_handler
from tg_hub_bot.services.reminders import RemindersService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ——— Создание Bot и Dispatcher ———
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# ——— Инициализация сервисов (БД, AI, напоминания, scheduler) ———
tasks_repo = get_tasks_repo()
reminders_service = RemindersService(bot, tasks_repo)
ai_service = create_ai_service()
scheduler = create_scheduler(reminders_service)

# ——— Регистрация хендлеров ———
register_start_handler(dp, WEBAPP_HUB_URL)
register_ai_chat_handler(dp, ai_service)


async def main() -> None:
    logger.info("Запуск бота...")
    start_scheduler(scheduler)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
