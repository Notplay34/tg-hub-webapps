"""
Инициализация доступа к БД для бота.

Путь к БД и фабрика репозитория задач — единственная точка входа для работы с хранилищем.
"""

from pathlib import Path

from tg_hub_bot.repositories.tasks import SqliteTaskRepository

DATABASE = Path("data/hub.db")


def get_tasks_repo() -> SqliteTaskRepository:
    """Возвращает репозиторий задач для напоминаний (SQLite)."""
    return SqliteTaskRepository(str(DATABASE))
