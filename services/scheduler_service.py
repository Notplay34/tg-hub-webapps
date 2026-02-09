"""
Инициализация планировщика напоминаний.

Реэкспорт из tg_hub_bot: создание и запуск scheduler.
Вся логика расписания (9:00, 12:00, 20:00, каждую минуту) — в tg_hub_bot.scheduler.

This module acts as an isolation layer for scheduler implementation
(anti-corruption: bot depends on services.*, not directly on tg_hub_bot.scheduler).
"""

from tg_hub_bot.scheduler import create_scheduler as _create_scheduler
from tg_hub_bot.scheduler import start_scheduler as _start_scheduler


def create_scheduler(reminders_service):
    """Создаёт и настраивает планировщик (не запускает)."""
    return _create_scheduler(reminders_service)


def start_scheduler(scheduler) -> None:
    """Запускает планировщик."""
    _start_scheduler(scheduler)
