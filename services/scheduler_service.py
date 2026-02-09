"""
Сервис планировщика напоминаний.

bot.py только вызывает scheduler_service.start() и не знает про APScheduler.
Handlers работают с SchedulerService (add_reminder / remove_reminder при необходимости).

This module acts as an isolation layer for scheduler implementation
(anti-corruption: bot depends on services.*, not directly on tg_hub_bot.scheduler).
"""

from tg_hub_bot.scheduler import SchedulerService


def create_scheduler_service(reminders_service):
    """Создаёт SchedulerService: инициализация и регистрация задач внутри сервиса."""
    return SchedulerService(reminders_service)
