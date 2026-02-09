"""
Хендлер текстовых сообщений → ИИ. ARCH: только вызов ai_service и ответ пользователю.
"""
from __future__ import annotations

from aiogram import F, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import Message

from tg_hub_bot.services.ai import AiService


async def _handle_chat_with_ai(message: Message, ai_service: AiService) -> None:
    """
    Любой текст (кроме команд) — общение с ИИ.

    Можно диктовать голосом в поле ввода Telegram — бот получает текст.
    """
    text = (message.text or "").strip()
    # Команды (начинаются с /) не трогаем — вдруг появятся другие хендлеры
    if not text or text.startswith("/"):
        return

    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    await message.answer("🧠 Думаю...")
    answer = await ai_service.generate_response(user_id, text)
    await message.answer(answer, parse_mode=ParseMode.HTML)


def register_ai_chat_handler(dp: Dispatcher, ai_service: AiService) -> None:
    """Регистрирует хендлер сообщений, которые идут в ИИ. Регистрировать ПОСЛЕ /start."""

    @dp.message(F.text)
    async def chat_with_ai(message: Message) -> None:  # noqa: D401
        """Любой текст — при командах (/) просто выходим, остальное в ИИ."""
        await _handle_chat_with_ai(message, ai_service)

