"""
Хендлер команды /start — приветствие и Hub.

Перед приветствием — оплата Stars (если ещё не оплатил).
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from config import PAYMENT_STARS
from storage.bootstrap import get_paid_repo
from tg_hub_bot.handlers.payment import send_invoice

logger = logging.getLogger(__name__)


def get_hub_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    """Кнопка «Открыть Hub» — Web App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть Hub", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


async def _send_welcome(bot: Bot, chat_id: int, webapp_url: str | None) -> None:
    """Отправляет приветственное сообщение с кнопкой Hub."""
    text = (
        "👋 <b>YouHub</b> — задачи, проекты и финансы в одном месте.\n\n"
        "Задачи, которые не теряются. Проекты с живым прогрессом. "
        "Деньги — видно куда ушло и откуда пришло.\n\n"
        "Пиши текстом — бот поймёт. Или нажми кнопку — откроется Hub."
    )
    if not webapp_url:
        text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"

    if webapp_url:
        await bot.send_message(
            chat_id,
            text,
            reply_markup=get_hub_keyboard(webapp_url),
        )
    else:
        await bot.send_message(chat_id, text)


def register_start_handler(
    dp: Dispatcher,
    bot: Bot,
    webapp_url: str | None = None,
) -> None:
    """Регистрирует хендлер /start. Проверка оплаты → invoice или приветствие."""

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not user_id:
            return

        try:
            if PAYMENT_STARS <= 0:
                await _send_welcome(bot, message.chat.id, webapp_url)
                return

            paid_repo = get_paid_repo()
            if await paid_repo.is_paid(user_id):
                await _send_welcome(bot, message.chat.id, webapp_url)
            else:
                await send_invoice(bot, message.chat.id, user_id)
        except Exception as e:
            logger.exception("cmd_start error: %s", e)
            try:
                await _send_welcome(bot, message.chat.id, webapp_url)
            except Exception:
                await bot.send_message(
                    message.chat.id,
                    "Ошибка. Попробуйте /start ещё раз.",
                )
