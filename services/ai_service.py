"""
Инициализация сервиса общения с ИИ.

Использует API TG Hub (/api/chat). Создание инстанса вынесено сюда,
чтобы bot.py не знал деталей конфигурации AI.
"""

from config import API_BASE_URL
from tg_hub_bot.services.ai import ApiAiService


def create_ai_service(timeout_seconds: int = 30) -> ApiAiService:
    """Создаёт и возвращает сервис для запросов к ИИ через API."""
    return ApiAiService(API_BASE_URL, timeout_seconds=timeout_seconds)
