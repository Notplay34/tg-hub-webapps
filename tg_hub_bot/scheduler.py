"""
Сервис планировщика напоминаний.

Инкапсулирует APScheduler: инициализация, регистрация задач, start.
Handlers и bot.py работают только с SchedulerService (start, add_reminder, remove_reminder).
В будущем можно заменить на внешний воркер без изменения вызывающего кода.
"""

# ⚠️ Infrastructure boundary: APScheduler implementation
# Do not import this module outside services layer


from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger


logger = logging.getLogger(__name__)


class RemindersServiceProtocol(Protocol):
    """Минимальный интерфейс сервиса напоминаний для планировщика."""

    async def send_morning_reminder(self) -> None: ...

    async def send_evening_reminder(self) -> None: ...

    async def send_overdue_reminder(self) -> None: ...

    async def send_reminders_by_time(self) -> None: ...


class SchedulerServiceProtocol(Protocol):
    """Интерфейс сервиса планировщика. Замена на внешний воркер — новая реализация без смены handlers."""

    def start(self) -> None: ...

    def add_reminder(self, job_id: str, callback: Callable[[], Any], *, trigger: BaseTrigger) -> None: ...

    def remove_reminder(self, job_id: str) -> bool: ...


class SchedulerService:
    """
    Сервис планировщика: запуск и управление напоминаниями.

    Реализует SchedulerServiceProtocol. bot.py только вызывает .start().
    Handlers используют add_reminder/remove_reminder при необходимости.
    Реализация (APScheduler) скрыта; можно заменить на внешний воркер.
    """

    def __init__(self, reminders_service: RemindersServiceProtocol) -> None:
        self._reminders = reminders_service
        self._scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        self._register_default_jobs()

    def _register_default_jobs(self) -> None:
        """Регистрирует стандартные напоминания (9:00, 12:00, 20:00, каждую минуту)."""
        self._scheduler.add_job(
            self._reminders.send_morning_reminder,
            CronTrigger(hour=9, minute=0),
            id="morning_reminder",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._reminders.send_evening_reminder,
            CronTrigger(hour=20, minute=0),
            id="evening_reminder",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._reminders.send_overdue_reminder,
            CronTrigger(hour=12, minute=0),
            id="overdue_reminder",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._reminders.send_reminders_by_time,
            CronTrigger(minute="*"),
            id="time_based_reminder",
            replace_existing=True,
        )
        logger.info(
            "Scheduler настроен: 9:00, 12:00, 20:00 и каждую минуту для персональных напоминаний",
        )

    def start(self) -> None:
        """Запускает планировщик. Единственный метод, который вызывает bot.py."""
        if self._scheduler.running:
            logger.info("Scheduler уже запущен, повторный старт пропущен")
            return
        logger.info("Запуск scheduler для напоминаний...")
        self._scheduler.start()

    def add_reminder(
        self,
        job_id: str,
        callback: Callable[[], Any],
        *,
        trigger: BaseTrigger,
    ) -> None:
        """Добавить задачу напоминания (для handlers и будущего расширения)."""
        self._scheduler.add_job(callback, trigger, id=job_id, replace_existing=True)

    def remove_reminder(self, job_id: str) -> bool:
        """Удалить задачу по id. Возвращает True, если задача была удалена."""
        try:
            self._scheduler.remove_job(job_id)
            return True
        except Exception:  # noqa: BLE001
            return False
