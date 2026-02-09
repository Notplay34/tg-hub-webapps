from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import aiohttp

from config import API_BASE_URL


logger = logging.getLogger(__name__)


@runtime_checkable
class AiService(Protocol):
    """Интерфейс сервиса общения с ИИ для Telegram-бота."""

    async def ask(self, user_id: str | int, text: str) -> str:  # pragma: no cover - протокол
        ...


class ApiAiService:
    """
    Реализация AiService, обращающаяся к API TG Hub (/api/chat).

    Использует тот же ассистент, что и веб-приложение.
    """

    def __init__(self, base_url: str | None = None, *, timeout_seconds: int = 30) -> None:
        self._base_url = (base_url or API_BASE_URL).rstrip("/")
        self._timeout = timeout_seconds

    async def ask(self, user_id: str | int, text: str) -> str:
        """
        Отправляет запрос в /api/chat и возвращает текст ответа.

        В случае ошибок вернёт дружелюбное сообщение для пользователя.
        """
        url = f"{self._base_url}/api/chat"
        payload = {"message": text}
        headers = {
            "Content-Type": "application/json",
            "X-User-Id": str(user_id),
        }

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"HTTP {resp.status}: {body}")
                    data = await resp.json()
        except Exception:  # noqa: BLE001
            logger.exception("AI request failed")
            return "❌ Не получилось обратиться к ИИ. Попробуй ещё раз чуть позже."

        answer = data.get("response")
        if not answer:
            return "😕 ИИ не прислал ответа."

        return answer

