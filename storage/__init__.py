"""Хранилище и инициализация доступа к БД бота."""

from storage.bootstrap import DATABASE, get_database_provider, get_tasks_repo

__all__ = ["DATABASE", "get_database_provider", "get_tasks_repo"]
