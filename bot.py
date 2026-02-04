"""
TG Hub — главный файл бота.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, WEBAPP_TASKS_URL, WEBAPP_PEOPLE_URL, WEBAPP_KNOWLEDGE_URL

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Бот и диспетчер
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с Web Apps."""
    # Кнопка Список дел
    if WEBAPP_TASKS_URL:
        tasks_btn = KeyboardButton(
            text="📋 Список дел",
            web_app=WebAppInfo(url=WEBAPP_TASKS_URL)
        )
    else:
        tasks_btn = KeyboardButton(text="📋 Список дел")
    
    # Кнопка Картотека
    if WEBAPP_PEOPLE_URL:
        people_btn = KeyboardButton(
            text="👤 Картотека",
            web_app=WebAppInfo(url=WEBAPP_PEOPLE_URL)
        )
    else:
        people_btn = KeyboardButton(text="👤 Картотека")
    
    # Кнопка База знаний
    if WEBAPP_KNOWLEDGE_URL:
        knowledge_btn = KeyboardButton(
            text="📚 База знаний",
            web_app=WebAppInfo(url=WEBAPP_KNOWLEDGE_URL)
        )
    else:
        knowledge_btn = KeyboardButton(text="📚 База знаний")
    
    buttons = [
        [tasks_btn],
        [people_btn, knowledge_btn]
    ]
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start."""
    await message.answer(
        "⚡ <b>Hub</b>\n\n"
        "Всё важное — в одном месте.\n"
        "Люди, задачи, знания — под контролем.",
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "👤 Картотека")
async def msg_people(message: Message):
    """Картотека — fallback."""
    await message.answer("👤 <b>Картотека</b>\n\nНастройте WEBAPP_PEOPLE_URL")


@dp.message(F.text == "📚 База знаний")
async def msg_knowledge(message: Message):
    """База знаний — fallback."""
    await message.answer("📚 <b>База знаний</b>\n\nНастройте WEBAPP_KNOWLEDGE_URL")


@dp.message(F.text == "📋 Список дел")
async def msg_tasks(message: Message):
    """Список дел — fallback."""
    await message.answer("📋 <b>Список дел</b>\n\nНастройте WEBAPP_TASKS_URL")


async def main():
    """Запуск бота."""
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
