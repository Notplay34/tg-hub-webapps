"""
Инициализация Telegram-бота YouHub.

Тонкий слой: создание Bot/Dispatcher, DI (репозитории, сервисы, scheduler),
регистрация хендлеров и точка запуска run().
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import API_BASE_URL, BOT_TOKEN, WEBAPP_HUB_URL
from storage.bootstrap import get_tasks_repo
from tg_hub_bot.handlers.start import register_start_handler
from tg_hub_bot.handlers.ai_chat import register_ai_chat_handler
from tg_hub_bot.scheduler import SchedulerService
from tg_hub_bot.services.ai import ApiAiService
from tg_hub_bot.services.reminders import RemindersService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
tasks_repo = get_tasks_repo()
reminders_service = RemindersService(bot, tasks_repo)
scheduler_service = SchedulerService(reminders_service)
ai_service = ApiAiService(API_BASE_URL)

# Регистрация хендлеров: /start обязательно ПЕРЕД F.text, иначе /start перехватит AI-чат
register_start_handler(dp, WEBAPP_HUB_URL)
register_ai_chat_handler(dp, ai_service)


async def run() -> None:
    """Точка запуска бота (раньше main() в bot.py)."""
    logger.info("Запуск бота...")

    scheduler_service.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
