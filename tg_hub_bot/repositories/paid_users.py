"""
Репозиторий оплативших пользователей (Telegram Stars).

Проверка доступа и сохранение после успешной оплаты.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import aiosqlite

if TYPE_CHECKING:
    from storage.database import DatabaseProvider


@runtime_checkable
class PaidUsersRepository(Protocol):
    """Интерфейс репозитория оплативших пользователей."""

    async def is_paid(self, user_id: str) -> bool:
        ...

    async def mark_paid(self, user_id: str, telegram_payment_charge_id: str) -> None:
        ...


class SqlitePaidUsersRepository(PaidUsersRepository):
    """Репозиторий на базе SQLite. Таблица paid_users создаётся при первом использовании."""

    def __init__(self, db_provider: "DatabaseProvider") -> None:
        self._provider = db_provider

    async def _ensure_table(self, db: aiosqlite.Connection) -> None:
        """Создаёт таблицу если её нет (бот может стартовать до API)."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paid_users (
                user_id TEXT PRIMARY KEY,
                telegram_payment_charge_id TEXT,
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

    async def is_paid(self, user_id: str) -> bool:
        async with self._provider.connection() as db:
            await self._ensure_table(db)
            cursor = await db.execute(
                "SELECT 1 FROM paid_users WHERE user_id = ? LIMIT 1",
                (str(user_id),),
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_paid(self, user_id: str, telegram_payment_charge_id: str) -> None:
        async with self._provider.connection() as db:
            await self._ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO paid_users (user_id, telegram_payment_charge_id, paid_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (str(user_id), telegram_payment_charge_id),
            )
            await db.commit()
