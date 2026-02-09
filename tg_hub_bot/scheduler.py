from __future__ import annotations

import logging
from typing import Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


logger = logging.getLogger(__name__)


class RemindersServiceProtocol(Protocol):
    """
    Минимальный интерфейс сервиса напоминаний,
    который нужен планировщику.
    """

    async def send_morning_reminder(self) -> None: ...

    async def send_evening_reminder(self) -> None: ...

    async def send_overdue_reminder(self) -> None: ...

    async def send_reminders_by_time(self) -> None: ...


def create_scheduler(reminders_service: RemindersServiceProtocol) -> AsyncIOScheduler:
    """
    Создаёт и настраивает планировщик, но НЕ запускает его.

    Вся логика расписания сосредоточена здесь, чтобы в будущем
    можно было вынести scheduler в отдельный процесс/воркер.
    """
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Утром в 9:00 — задачи на сегодня
    scheduler.add_job(
        reminders_service.send_morning_reminder,
        CronTrigger(hour=9, minute=0),
        id="morning_reminder",
        replace_existing=True,
    )

    # Вечером в 20:00 — задачи на завтра
    scheduler.add_job(
        reminders_service.send_evening_reminder,
        CronTrigger(hour=20, minute=0),
        id="evening_reminder",
        replace_existing=True,
    )

    # Днём в 12:00 — просроченные задачи
    scheduler.add_job(
        reminders_service.send_overdue_reminder,
        CronTrigger(hour=12, minute=0),
        id="overdue_reminder",
        replace_existing=True,
    )

    # Каждую минуту — персональное время из карточки задачи
    scheduler.add_job(
        reminders_service.send_reminders_by_time,
        CronTrigger(minute="*"),
        id="time_based_reminder",
        replace_existing=True,
    )

    logger.info(
        "Scheduler настроен: 9:00, 12:00, 20:00 и каждую минуту для персональных напоминаний",
    )

    return scheduler


def start_scheduler(scheduler: AsyncIOScheduler) -> None:
    """
    Запускает планировщик.

    Вынесено в отдельную функцию, чтобы можно было гибко управлять
    запуском (например, отключать scheduler в отдельных процессах).
    """
    if scheduler.running:
        logger.info("Scheduler уже запущен, повторный старт пропущен")
        return

    logger.info("Запуск scheduler для напоминаний...")
    scheduler.start()

