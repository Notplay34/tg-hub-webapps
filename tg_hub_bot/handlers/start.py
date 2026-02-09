"""
Хендлер команды /start и клавиатуры: inline (Web App) и reply (быстрые действия).

ARCH: только регистрация команды и формат ответа (текст, клавиатура).
Бизнес-логику не добавлять — в services.
"""

from __future__ import annotations

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


def get_reply_keyboard(webapp_url: str | None) -> ReplyKeyboardMarkup:
    """
    Постоянная клавиатура под полем ввода: быстрые действия.
    Нажатие отправляет текст боту — ИИ отвечает по контексту (задачи, финансы и т.д.).
    """
    row1 = [
        KeyboardButton(text="📋 Что сегодня?"),
        KeyboardButton(text="💰 Итоги по деньгам"),
    ]
    row2 = [
        KeyboardButton(text="🎯 Мои цели"),
        KeyboardButton(text="🤖 Задать вопрос"),
    ]
    keyboard = [row1, row2]
    if webapp_url:
        keyboard.append([KeyboardButton(text="🌐 Открыть Hub", web_app=WebAppInfo(url=webapp_url))])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Напиши задачу, расход или вопрос...",
    )


def get_main_keyboard(webapp_url: str | None) -> InlineKeyboardMarkup | None:
    """Кнопка «Старт» — открывает Hub Web App."""
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Открыть Hub", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


def register_start_handler(dp: Dispatcher, webapp_url: str | None = None) -> None:
    """Регистрирует хендлер команды /start."""

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        # Сначала показываем постоянную клавиатуру (останется под полем ввода)
        await message.answer(
            "👋 <b>YouHub</b> — твой личный хаб: задачи, люди, деньги и ИИ в одном месте.",
            reply_markup=get_reply_keyboard(webapp_url),
        )
        text = (
            "Можешь <b>нажать кнопку ниже</b> — бот ответит по твоим данным. "
            "Или написать своим словами: «добавь задачу купить молоко», «потратил 500 на обед», «что у меня сегодня?»\n\n"
            "📋 Задачи · 👤 Люди · 📚 База знаний · 💰 Финансы · 🤖 ИИ-ассистент\n\n"
            "Полный интерфейс — по кнопке <b>Открыть Hub</b>."
        )
        if not webapp_url:
            text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
        await message.answer(text, reply_markup=get_main_keyboard(webapp_url))
