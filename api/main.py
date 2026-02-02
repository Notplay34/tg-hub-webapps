"""
API для TG Hub — хранение данных.
"""

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import aiosqlite
import json
from datetime import datetime
from pathlib import Path

app = FastAPI(title="TG Hub API")

# CORS для Web Apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE = "data/hub.db"


# === Модели ===

class Task(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None
    priority: str = "medium"
    done: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    done: Optional[bool] = None


class Person(BaseModel):
    fio: str
    birth_date: Optional[str] = None
    relation: Optional[str] = None
    workplace: Optional[str] = None
    financial: Optional[str] = None
    strengths: Optional[str] = None
    weaknesses: Optional[str] = None
    benefits: Optional[str] = None
    problems: Optional[str] = None
    groups: Optional[list] = []
    connections: Optional[list] = []


class Note(BaseModel):
    text: str


# === База данных ===

async def init_db():
    """Инициализация БД."""
    Path("data").mkdir(exist_ok=True)
    
    async with aiosqlite.connect(DATABASE) as db:
        # Таблица задач
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                deadline DATE,
                priority TEXT DEFAULT 'medium',
                done INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица людей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица заметок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
        """)
        
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()


def get_user_id(x_user_id: str = Header(...)) -> str:
    """Получить user_id из заголовка."""
    return x_user_id


# === Задачи ===

@app.get("/api/tasks")
async def get_tasks(x_user_id: str = Header(...)):
    """Получить все задачи пользователя."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
            (x_user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@app.post("/api/tasks")
async def create_task(task: Task, x_user_id: str = Header(...)):
    """Создать задачу."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            """INSERT INTO tasks (user_id, title, description, deadline, priority, done)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (x_user_id, task.title, task.description, task.deadline, task.priority, int(task.done))
        )
        await db.commit()
        return {"id": cursor.lastrowid, "message": "created"}


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate, x_user_id: str = Header(...)):
    """Обновить задачу."""
    async with aiosqlite.connect(DATABASE) as db:
        # Проверяем владельца
        cursor = await db.execute(
            "SELECT id FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        
        updates = []
        values = []
        for field, value in task.dict(exclude_unset=True).items():
            if value is not None:
                updates.append(f"{field} = ?")
                values.append(int(value) if isinstance(value, bool) else value)
        
        if updates:
            values.append(task_id)
            await db.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
                values
            )
            await db.commit()
        
        return {"message": "updated"}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, x_user_id: str = Header(...)):
    """Удалить задачу."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, x_user_id)
        )
        await db.commit()
        return {"message": "deleted"}


# === Люди ===

@app.get("/api/people")
async def get_people(x_user_id: str = Header(...)):
    """Получить всех людей."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM people WHERE user_id = ? ORDER BY created_at DESC",
            (x_user_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            person = dict(row)
            person['data'] = json.loads(person['data'])
            # Получаем заметки
            notes_cursor = await db.execute(
                "SELECT id, text, created_at FROM notes WHERE person_id = ? ORDER BY created_at DESC",
                (person['id'],)
            )
            person['notes'] = [dict(n) for n in await notes_cursor.fetchall()]
            result.append(person)
        return result


@app.post("/api/people")
async def create_person(person: Person, x_user_id: str = Header(...)):
    """Создать карточку человека."""
    data = person.dict(exclude={'fio'})
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "INSERT INTO people (user_id, fio, data) VALUES (?, ?, ?)",
            (x_user_id, person.fio, json.dumps(data, ensure_ascii=False))
        )
        await db.commit()
        return {"id": cursor.lastrowid, "message": "created"}


@app.patch("/api/people/{person_id}")
async def update_person(person_id: int, person: Person, x_user_id: str = Header(...)):
    """Обновить карточку человека."""
    data = person.dict(exclude={'fio'})
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM people WHERE id = ? AND user_id = ?",
            (person_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")
        
        await db.execute(
            "UPDATE people SET fio = ?, data = ? WHERE id = ?",
            (person.fio, json.dumps(data, ensure_ascii=False), person_id)
        )
        await db.commit()
        return {"message": "updated"}


@app.delete("/api/people/{person_id}")
async def delete_person(person_id: int, x_user_id: str = Header(...)):
    """Удалить карточку человека."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "DELETE FROM people WHERE id = ? AND user_id = ?",
            (person_id, x_user_id)
        )
        await db.commit()
        return {"message": "deleted"}


# === Заметки ===

@app.post("/api/people/{person_id}/notes")
async def add_note(person_id: int, note: Note, x_user_id: str = Header(...)):
    """Добавить заметку к человеку."""
    async with aiosqlite.connect(DATABASE) as db:
        # Проверяем владельца
        cursor = await db.execute(
            "SELECT id FROM people WHERE id = ? AND user_id = ?",
            (person_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")
        
        cursor = await db.execute(
            "INSERT INTO notes (person_id, text) VALUES (?, ?)",
            (person_id, note.text)
        )
        await db.commit()
        return {"id": cursor.lastrowid, "message": "created"}


@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, x_user_id: str = Header(...)):
    """Удалить заметку."""
    async with aiosqlite.connect(DATABASE) as db:
        # Проверяем через join что заметка принадлежит пользователю
        cursor = await db.execute("""
            SELECT n.id FROM notes n
            JOIN people p ON n.person_id = p.id
            WHERE n.id = ? AND p.user_id = ?
        """, (note_id, x_user_id))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Note not found")
        
        await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await db.commit()
        return {"message": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
