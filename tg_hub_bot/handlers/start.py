"""
Хендлер команды /start — приветствие, Hub и быстрые кнопки.

Доступ всем.
"""

from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

logger = logging.getLogger(__name__)


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура: быстрые действия."""
    keyboard = [
        [KeyboardButton(text="📋 Что сегодня?"), KeyboardButton(text="💰 Итоги по деньгам")],
        [KeyboardButton(text="🎯 Мои цели"), KeyboardButton(text="📂 Сводка по проектам")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Добавь задачу, расход или спроси что угодно...",
    )


def get_hub_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    """Кнопка «Открыть Hub» — Web App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть Hub", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


def register_start_handler(dp: Dispatcher, webapp_url: str | None = None) -> None:
    """Регистрирует хендлер команды /start. Доступ всем — Hub + быстрые кнопки."""

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not user_id:
            return

        text = (
            "👋 <b>Привет!</b>\n\n"
            "Пиши <i>«добавь задачу купить молоко»</i>, <i>«расход 500 обед»</i>, "
            "<i>«что сегодня?»</i> — бот поймёт.\n\n"
            "📱 <b>«Открыть Hub»</b> — полный интерфейс: задачи, проекты, финансы.\n\n"
        )
        if not webapp_url:
            text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"

        # Сообщение с кнопкой Hub
        if webapp_url:
            await message.answer(text, reply_markup=get_hub_keyboard(webapp_url))
        else:
            await message.answer(text)

        # Reply-кнопки (Что сегодня, Итоги, и т.д.)
        await message.answer(
            "Быстрые кнопки:",
            reply_markup=get_reply_keyboard(),
        )
