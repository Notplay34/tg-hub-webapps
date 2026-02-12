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


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Постоянная клавиатура: быстрые действия.
    Hub только через inline — reply открывает без initData, данные не грузятся.
    """
    keyboard = [
        [KeyboardButton(text="📋 Что сегодня?"), KeyboardButton(text="💰 Итоги по деньгам")],
        [KeyboardButton(text="🎯 Мои цели"), KeyboardButton(text="🤖 Задать вопрос")],
    ]
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
        # Первое сообщение: inline "Открыть Hub" (важно — initData есть только у inline, не у reply)
        # Reply-клавиатура идёт вторым сообщением
        kwargs = {}
        if webapp_url:
            kwargs["reply_markup"] = get_main_keyboard(webapp_url)
        await message.answer(
            "👋 <b>YouHub</b> — твой личный хаб: задачи, люди, деньги и ИИ в одном месте.\n\n"
            "📱 <b>Нажми кнопку ниже</b> — откроется Hub с твоими задачами.",
            **kwargs,
        )
        await message.answer(
            "Клавиатура быстрых действий:",
            reply_markup=get_reply_keyboard(),
        )
        text = (
            "Можешь <b>нажать кнопку</b> — бот ответит по твоим данным. "
            "Или написать: «добавь задачу купить молоко», «потратил 500 на обед», «что у меня сегодня?»\n\n"
            "📋 Задачи · 👤 Люди · 📂 Проекты · 💰 Финансы · 🤖 ИИ"
        )
        if not webapp_url:
            text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
        await message.answer(text)
