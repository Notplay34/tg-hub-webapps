from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import aiohttp

from config import API_BASE_URL


logger = logging.getLogger(__name__)


@runtime_checkable
class AiService(Protocol):
    """Интерфейс AI-ассистента: единая точка входа для генерации ответа."""

    async def generate_response(self, user_id: str | int, message: str) -> str:
        """Сгенерировать ответ по сообщению пользователя (контекст и данные — внутри сервиса)."""
        ...

    async def ask(self, user_id: str | int, text: str) -> str:
        """Устаревший алиас; использовать generate_response."""
        ...


class ApiAiService:
    """
    Реализация AiService через API TG Hub (/api/chat).

    Контекст диалога и данные (задачи, люди, напоминания) — на стороне API.
    Бот только передаёт user_id и message.
    """

    def __init__(self, base_url: str | None = None, *, timeout_seconds: int = 30) -> None:
        self._base_url = (base_url or API_BASE_URL).rstrip("/")
        self._timeout = timeout_seconds

    async def generate_response(self, user_id: str | int, message: str) -> str:
        """Единый интерфейс: ответ по сообщению пользователя."""
        return await self._call_api(user_id, message)

    async def ask(self, user_id: str | int, text: str) -> str:
        """Алиас для generate_response (обратная совместимость)."""
        return await self.generate_response(user_id, text)

    async def _call_api(self, user_id: str | int, message: str) -> str:
        """Отправляет запрос в /api/chat, возвращает текст ответа или сообщение об ошибке."""
        url = f"{self._base_url}/api/chat"
        payload = {"message": message}
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

