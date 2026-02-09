from __future__ import annotations

from typing import Iterable, List, Dict, Sequence

import aiosqlite

# Используем такой же путь к БД, как и в основном API.
# Дублирование строки ок, чтобы не плодить циклические импорты.
DATABASE = "data/hub.db"


async def clear_history(user_id: str, db_path: str = DATABASE) -> None:
    """Удалить всю историю чата пользователя."""

    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        await db.commit()


async def delete_assistant_messages_with_phrase(
    user_id: str,
    phrase: str,
    db_path: str = DATABASE,
) -> int:
    """
    Удалить сообщения ассистента, содержащие фразу (регистронезависимо).

    Возвращает количество удалённых сообщений.
    """

    async with aiosqlite.connect(db_path) as db:
        like = f"%{phrase}%"
        cursor = await db.execute(
            """
            SELECT id, content
            FROM chat_history
            WHERE user_id = ?
              AND role = 'assistant'
              AND LOWER(content) LIKE ?
            """,
            (user_id, like),
        )
        rows = await cursor.fetchall()

        ids_to_delete: List[int] = []
        lower_phrase = phrase.lower()
        for row in rows:
            content_lower = (row[1] or "").lower()
            if lower_phrase in content_lower:
                ids_to_delete.append(row[0])

        if not ids_to_delete:
            return 0

        placeholders = ",".join("?" for _ in ids_to_delete)
        params: List[object] = [user_id, *ids_to_delete]
        await db.execute(
            f"DELETE FROM chat_history WHERE user_id = ? AND id IN ({placeholders})",
            params,
        )
        await db.commit()
        return len(ids_to_delete)


async def get_recent_history(
    user_id: str,
    limit: int,
    db_path: str = DATABASE,
) -> List[Dict[str, str]]:
    """
    Получить последние `limit` сообщений диалога в хронологическом порядке.
    Возвращает список словарей с ключами `role` и `content`.
    """

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT role, content
            FROM chat_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()

    # Разворачиваем в хронологическом порядке (от старых к новым)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def append_messages(
    user_id: str,
    messages: Iterable[tuple[str, str]],
    db_path: str = DATABASE,
) -> None:
    """Добавить несколько сообщений в историю (role, content)."""

    async with aiosqlite.connect(db_path) as db:
        for role, content in messages:
            await db.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
        await db.commit()


async def append_turn_and_trim(
    user_id: str,
    user_text: str,
    assistant_text: str,
    limit: int,
    db_path: str = DATABASE,
) -> None:
    """
    Добавить одну реплику пользователя и ответ ассистента, после чего
    обрезать историю до последних `limit` сообщений.
    """

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, "user", user_text),
        )
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, "assistant", assistant_text),
        )
        await db.execute(
            """
            DELETE FROM chat_history
            WHERE user_id = ?
              AND id NOT IN (
                SELECT id FROM chat_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
              )
            """,
            (user_id, user_id, limit),
        )
        await db.commit()


async def get_total_count(user_id: str, db_path: str = DATABASE) -> int:
    """Подсчитать количество сообщений в истории пользователя."""

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT COUNT(*) AS cnt FROM chat_history WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0


async def get_oldest_messages(
    user_id: str,
    limit: int,
    db_path: str = DATABASE,
) -> List[Dict[str, object]]:
    """
    Получить самые старые `limit` сообщений истории.
    Возвращает список словарей с полями id, role, content.
    """

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, role, content
            FROM chat_history
            WHERE user_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def insert_system_message(
    user_id: str,
    content: str,
    db_path: str = DATABASE,
) -> None:
    """Добавить системное сообщение (резюме) в историю чата."""

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, "system", content),
        )
        await db.commit()


async def delete_messages_by_ids(
    user_id: str,
    ids: Sequence[int],
    db_path: str = DATABASE,
) -> None:
    """Удалить сообщения по списку id для пользователя."""

    if not ids:
        return

    async with aiosqlite.connect(db_path) as db:
        placeholders = ",".join("?" for _ in ids)
        params: List[object] = [user_id, *ids]
        await db.execute(
            f"DELETE FROM chat_history WHERE user_id = ? AND id IN ({placeholders})",
            params,
        )
        await db.commit()

