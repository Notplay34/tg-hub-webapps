"""
TG Hub — Telegram бот YouHub. Точка входа: только запуск и wiring.

ARCH: Здесь ТОЛЬКО создание Bot/Dispatcher, вызов фабрик сервисов,
регистрация handlers, scheduler_service.start(), polling.
Запрещено: бизнес-логика, SQL, детали APScheduler/БД, условия по домену.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, WEBAPP_HUB_URL
from storage.bootstrap import get_tasks_repo
from services.ai_service import create_ai_service
from services.scheduler_service import create_scheduler_service
from tg_hub_bot.handlers.payment import register_payment_handlers
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
scheduler_service = create_scheduler_service(reminders_service)

# ——— Регистрация хендлеров ———
register_start_handler(dp, bot, WEBAPP_HUB_URL)
register_payment_handlers(dp, bot, WEBAPP_HUB_URL)
register_ai_chat_handler(dp, ai_service)


async def main() -> None:
    logger.info("Запуск бота...")
    scheduler_service.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
