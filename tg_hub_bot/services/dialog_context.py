"""
Контекст диалога для AI-ассистента.

Основная история хранится в API (chat_history). Здесь — опциональный
бот-сайд кэш для сессии (например last_intent, last_topic) для будущей проактивности.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class DialogContextManager:
    """
    Хранит контекст диалога по user_id (опционально).

    API уже ведёт полную историю в chat_history. Этот менеджер можно использовать
    для бот-сайд подсказок (например, последняя тема для проактивных предложений).
    """

    def __init__(self, max_entries_per_user: int = 10) -> None:
        self._max = max_entries_per_user
        self._store: Dict[str, Dict[str, Any]] = {}

    def get_context(self, user_id: str | int) -> Dict[str, Any]:
        """Возвращает контекст пользователя для передачи в AI (если нужно)."""
        key = str(user_id)
        return self._store.get(key) or {}

    def set(self, user_id: str | int, key: str, value: Any) -> None:
        """Сохранить значение в контексте пользователя."""
        k = str(user_id)
        if k not in self._store:
            self._store[k] = {}
        self._store[k][key] = value

    def append_turn(self, user_id: str | int, role: str, content: str) -> None:
        """Уведомить о новом повороте диалога (для будущей проактивности)."""
        # Пока не сохраняем локально — история в API
        pass
