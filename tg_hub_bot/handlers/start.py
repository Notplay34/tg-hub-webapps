"""
Хендлер команды /start и клавиатура с кнопкой Web App.

ARCH: только регистрация команды и формат ответа (текст, клавиатура).
Бизнес-логику не добавлять — в services.
"""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)


def get_main_keyboard(webapp_url: str | None) -> InlineKeyboardMarkup | None:
    """Кнопка «Старт» — открывает Hub Web App."""
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Старт", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


def register_start_handler(dp: Dispatcher, webapp_url: str | None = None) -> None:
    """Регистрирует хендлер команды /start."""

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
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
        if not webapp_url:
            text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
        await message.answer(text, reply_markup=get_main_keyboard(webapp_url))
