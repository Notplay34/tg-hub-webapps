"""
TG Hub — Telegram бот с единым Web App.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, WEBAPP_HUB_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура с кнопкой открытия Hub."""
    if WEBAPP_HUB_URL:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚀 Открыть Hub",
                web_app=WebAppInfo(url=WEBAPP_HUB_URL)
            )]
        ])
    return None


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start."""
    # Убираем Reply клавиатуру
    await message.answer("⚡", reply_markup=ReplyKeyboardRemove())
    
    text = (
        "⚡ <b>Hub</b>\n\n"
        "Твой персональный центр управления:\n\n"
        "📋 <b>Задачи</b> — планируй и выполняй\n"
        "👤 <b>Картотека</b> — досье на людей\n"
        "📚 <b>База знаний</b> — храни важное\n"
        "🤖 <b>ИИ-ассистент</b> — скоро\n\n"
        "Нажми кнопку ниже, чтобы начать."
    )
    
    kb = get_main_keyboard()
    
    if not WEBAPP_HUB_URL:
        text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
    
    await message.answer(text, reply_markup=kb)


async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
