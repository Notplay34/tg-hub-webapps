"""
Единая точка доступа к БД: провайдер сессии/соединения.

Handlers и services не создают соединений — они работают только с репозиториями.
Репозитории получают соединение через DatabaseProvider. Замена SQLite на PostgreSQL
сводится к новой реализации провайдера и репозиториев без изменения handlers/services.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncContextManager, Any, Protocol

import aiosqlite


class DatabaseProvider(Protocol):
    """
    Провайдер соединения с БД.

    Используется при старте приложения; репозитории получают провайдер
    и вызывают connection() внутри методов (get, list, add, delete).
    """

    def connection(self) -> AsyncContextManager[Any]:
        """Возвращает асинхронный контекст-менеджер соединения."""
        ...


class AiosqliteDatabaseProvider:
    """Провайдер соединений SQLite через aiosqlite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @asynccontextmanager
    async def connection(self) -> AsyncContextManager[aiosqlite.Connection]:
        async with aiosqlite.connect(self._db_path) as conn:
            yield conn
