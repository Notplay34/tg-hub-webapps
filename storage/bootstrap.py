"""
Инициализация доступа к БД для бота.

ARCH: только фабрики (get_database_provider, get_tasks_repo). Никакой
бизнес-логики и SQL. Handlers и bot.py не создают соединений.
"""

from pathlib import Path
from typing import Optional

from storage.database import AiosqliteDatabaseProvider, DatabaseProvider
from tg_hub_bot.repositories.paid_users import PaidUsersRepository, SqlitePaidUsersRepository
from tg_hub_bot.repositories.tasks import SqliteTaskRepository, TaskRepository

DATABASE = Path("data/hub.db")

_provider: Optional[DatabaseProvider] = None


def get_database_provider() -> DatabaseProvider:
    """Единый провайдер соединений с БД (используется при старте приложения)."""
    global _provider
    if _provider is None:
        _provider = AiosqliteDatabaseProvider(str(DATABASE))
    return _provider


def get_tasks_repo() -> TaskRepository:
    """Возвращает репозиторий задач для напоминаний."""
    return SqliteTaskRepository(get_database_provider())


def get_paid_repo() -> PaidUsersRepository:
    """Возвращает репозиторий оплативших пользователей."""
    return SqlitePaidUsersRepository(get_database_provider())
