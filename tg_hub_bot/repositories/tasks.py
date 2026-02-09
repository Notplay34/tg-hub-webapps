"""
Репозиторий задач для напоминаний. ARCH: весь SQL по задачам — только здесь.
Handlers и services не пишут SQL; используют TaskRepository.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import aiosqlite

from tg_hub_bot.models import TaskSummary

if TYPE_CHECKING:
    from storage.database import DatabaseProvider


@runtime_checkable
class TaskRepository(Protocol):
    """Интерфейс репозитория задач. Только методы get/list — без SQL и деталей БД."""

    async def get_tasks_for_date(self, for_date: date) -> list[TaskSummary]:
        ...

    async def get_overdue_tasks(self, today: date) -> list[TaskSummary]:
        ...

    async def get_tasks_for_reminder_time(
        self,
        today: date,
        tomorrow: date,
        time_str: str,
        before_key: str,
    ) -> list[TaskSummary]:
        ...


class SqliteTaskRepository(TaskRepository):
    """
    Репозиторий задач на базе SQLite.

    Получает соединение через DatabaseProvider; вся работа с БД и SQL
    инкапсулирована здесь. Handlers и services не видят ни SQL, ни aiosqlite.
    """

    def __init__(self, db_provider: "DatabaseProvider") -> None:
        self._provider = db_provider

    async def get_tasks_for_date(self, for_date: date) -> list[TaskSummary]:
        date_str = for_date.isoformat()
        async with self._provider.connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT user_id, title, deadline, priority
                FROM tasks
                WHERE deadline = ? AND done = 0
                """,
                (date_str,),
            )
            rows = await cursor.fetchall()
        return [
            TaskSummary(
                user_id=str(row["user_id"]),
                title=row["title"],
                deadline=row["deadline"],
                priority=row["priority"],
            )
            for row in rows
        ]

    async def get_overdue_tasks(self, today: date) -> list[TaskSummary]:
        today_str = today.isoformat()
        async with self._provider.connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT user_id, title, deadline, priority
                FROM tasks
                WHERE deadline < ? AND done = 0
                """,
                (today_str,),
            )
            rows = await cursor.fetchall()
        return [
            TaskSummary(
                user_id=str(row["user_id"]),
                title=row["title"],
                deadline=row["deadline"],
                priority=row["priority"],
            )
            for row in rows
        ]

    async def get_tasks_for_reminder_time(
        self,
        today: date,
        tomorrow: date,
        time_str: str,
        before_key: str,
    ) -> list[TaskSummary]:
        today_str = today.isoformat()
        tomorrow_str = tomorrow.isoformat()
        async with self._provider.connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT user_id, title, reminder_time, deadline
                FROM tasks
                WHERE done = 0
                  AND reminder_enabled = 1
                  AND (
                    (deadline = ? AND reminder_time = ?)
                    OR
                    (deadline = ? AND reminder_time = ?)
                  )
                """,
                (today_str, time_str, tomorrow_str, before_key),
            )
            rows = await cursor.fetchall()
        return [
            TaskSummary(
                user_id=str(row["user_id"]),
                title=row["title"],
                deadline=row["deadline"],
                reminder_time=row["reminder_time"],
            )
            for row in rows
        ]

