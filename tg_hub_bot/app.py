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
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from config import API_BASE_URL, BOT_TOKEN, WEBAPP_HUB_URL
from tg_hub_bot.handlers.ai_chat import register_ai_chat_handler
from tg_hub_bot.repositories.tasks import SqliteTaskRepository
from tg_hub_bot.scheduler import create_scheduler, start_scheduler
from tg_hub_bot.services.ai import ApiAiService
from tg_hub_bot.services.reminders import RemindersService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = "data/hub.db"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
tasks_repo = SqliteTaskRepository(DATABASE)
reminders_service = RemindersService(bot, tasks_repo)
scheduler = create_scheduler(reminders_service)
ai_service = ApiAiService(API_BASE_URL)

# Регистрация хендлеров
register_ai_chat_handler(dp, ai_service)


def get_main_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка Старт — открывает приложение (для новых и текущих пользователей)."""
    if WEBAPP_HUB_URL:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="▶️ Старт",
                        web_app=WebAppInfo(url=WEBAPP_HUB_URL),
                    )
                ]
            ]
        )
    return None


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Команда /start — продающий экран для новых пользователей."""
    await message.answer("🧠 YouHub", reply_markup=ReplyKeyboardRemove())

    text = (
        "👋 <b>YouHub</b> — личный хаб: задачи, люди, деньги и ИИ в одном боте.\n\n"
        "Что внутри:\n\n"
        "📋 <b>Задачи</b> — дедлайны, приоритеты, напоминания\n"
        "👤 <b>Люди</b> — досье, связи, заметки\n"
        "📚 <b>База знаний</b> — важное под рукой\n"
        "💰 <b>Финансы</b> — доходы, расходы, цели и лимиты\n"
        "🤖 <b>ИИ-ассистент</b> — можешь просто написать боту вопрос, он ответит по твоим данным.\n\n"
        "Нажми <b>Старт</b> — и за 30 секунд настроишь всё под себя."
    )

    kb = get_main_keyboard()

    if not WEBAPP_HUB_URL:
        text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"

    await message.answer(text, reply_markup=kb)


async def run() -> None:
    """Точка запуска бота (раньше main() в bot.py)."""
    logger.info("Запуск бота...")

    start_scheduler(scheduler)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
