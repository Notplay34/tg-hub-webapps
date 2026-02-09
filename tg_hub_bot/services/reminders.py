from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List

from aiogram import Bot
from aiogram.enums import ParseMode

from tg_hub_bot.models import TaskSummary
from tg_hub_bot.repositories.tasks import TaskRepository


logger = logging.getLogger(__name__)


class RemindersService:
    """Сервис напоминаний о задачах."""

    def __init__(self, bot: Bot, tasks_repo: TaskRepository) -> None:
        self._bot = bot
        self._tasks_repo = tasks_repo

    async def send_reminders_by_time(self) -> None:
        """Напоминания по времени из карточки (запуск каждую минуту)."""
        now = datetime.now()
        today = now.date()
        time_str = now.strftime("%H:%M")
        tomorrow = now.date() + timedelta(days=1)
        before_key = f"before_{time_str}"

        tasks = await self._tasks_repo.get_tasks_for_reminder_time(
            today=today,
            tomorrow=tomorrow,
            time_str=time_str,
            before_key=before_key,
        )

        for task in tasks:
            try:
                if task.deadline == today.isoformat():
                    text = f"⏰ <b>Напоминание на сегодня</b>\n\n{task.title}"
                else:
                    text = f"⏰ <b>Напоминание: завтра срок</b>\n\n{task.title}"
                title_lower = (task.title or "").lower()
                if "встреча" in title_lower or "созвон" in title_lower or "звонок" in title_lower:
                    text += "\n\nПодготовиться?"
                await self._bot.send_message(int(task.user_id), text)
                logger.info(
                    "Напоминание по времени отправлено %s: %s",
                    task.user_id,
                    task.title,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Ошибка напоминания %s: %s", task.user_id, e)

    async def send_morning_reminder(self) -> None:
        """Утреннее напоминание о задачах на сегодня (9:00)."""
        logger.info("Отправка утренних напоминаний...")
        today = datetime.now().date()
        tasks = await self._tasks_repo.get_tasks_for_date(today)

        # Группируем по пользователям
        user_tasks: Dict[str, List[TaskSummary]] = {}
        for task in tasks:
            user_tasks.setdefault(task.user_id, []).append(task)

        for user_id, tasks_list in user_tasks.items():
            try:
                priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                text = "☀️ <b>Доброе утро!</b>\n\n"
                text += f"📋 Задачи на сегодня ({len(tasks_list)}):\n\n"
                for t in tasks_list:
                    icon = priority_icons.get(t.priority or "", "🟡")
                    text += f"{icon} {t.title}\n"

                await self._bot.send_message(int(user_id), text)
                logger.info("Напоминание отправлено пользователю %s", user_id)
            except Exception as e:  # noqa: BLE001
                logger.error("Ошибка отправки напоминания %s: %s", user_id, e)

    async def send_evening_reminder(self) -> None:
        """Вечернее напоминание о задачах на завтра (20:00)."""
        logger.info("Отправка вечерних напоминаний...")
        tomorrow = datetime.now().date() + timedelta(days=1)
        tasks = await self._tasks_repo.get_tasks_for_date(tomorrow)

        user_tasks: Dict[str, List[TaskSummary]] = {}
        for task in tasks:
            user_tasks.setdefault(task.user_id, []).append(task)

        for user_id, tasks_list in user_tasks.items():
            try:
                priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                text = "🌙 <b>Планы на завтра</b>\n\n"
                text += f"📋 Задачи ({len(tasks_list)}):\n\n"
                for t in tasks_list:
                    icon = priority_icons.get(t.priority or "", "🟡")
                    text += f"{icon} {t.title}\n"

                await self._bot.send_message(int(user_id), text)
                logger.info("Вечернее напоминание отправлено %s", user_id)
            except Exception as e:  # noqa: BLE001
                logger.error("Ошибка отправки напоминания %s: %s", user_id, e)

    async def send_overdue_reminder(self) -> None:
        """Напоминание о просроченных задачах (12:00)."""
        logger.info("Проверка просроченных задач...")
        today = datetime.now().date()
        tasks = await self._tasks_repo.get_overdue_tasks(today)

        user_tasks: Dict[str, List[TaskSummary]] = {}
        for task in tasks:
            user_tasks.setdefault(task.user_id, []).append(task)

        for user_id, tasks_list in user_tasks.items():
            try:
                text = "⚠️ <b>Просроченные задачи!</b>\n\n"
                for t in tasks_list:
                    text += f"⏰ {t.title} (до {t.deadline})\n"

                await self._bot.send_message(int(user_id), text, parse_mode=ParseMode.HTML)
                logger.info("Напоминание о просрочке отправлено %s", user_id)
            except Exception as e:  # noqa: BLE001
                logger.error("Ошибка отправки напоминания %s: %s", user_id, e)
