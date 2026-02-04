"""
API для TG Hub — хранение данных на сервере.
"""

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import json
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
    groups: Optional[List[str]] = []
    connections: Optional[List[int]] = []


class Note(BaseModel):
    text: str


class Knowledge(BaseModel):
    title: str
    content: Optional[str] = ""
    tags: Optional[List[str]] = []


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
        
        # Таблица заметок к людям
        await db.execute("""
            CREATE TABLE IF NOT EXISTS person_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
        """)
        
        # Таблица базы знаний
        await db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                tags TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()


# === ЗАДАЧИ ===

@app.get("/api/tasks")
async def get_tasks(x_user_id: str = Header(...)):
    """Получить все задачи."""
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
        return {"id": cursor.lastrowid}


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate, x_user_id: str = Header(...)):
    """Обновить задачу."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        
        updates = []
        values = []
        for field, value in task.dict(exclude_unset=True).items():
            if value is not None:
                updates.append(f"{field} = ?")
                values.append(int(value) if isinstance(value, bool) else value)
        
        if updates:
            values.append(task_id)
            await db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
            await db.commit()
        
        return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, x_user_id: str = Header(...)):
    """Удалить задачу."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, x_user_id))
        await db.commit()
        return {"ok": True}


# === ЛЮДИ ===

@app.get("/api/people")
async def get_people(x_user_id: str = Header(...)):
    """Получить всех людей."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM people WHERE user_id = ? ORDER BY created_at DESC", (x_user_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            person = dict(row)
            person['data'] = json.loads(person['data'])
            # Заметки
            notes_cursor = await db.execute(
                "SELECT id, text, created_at FROM person_notes WHERE person_id = ? ORDER BY created_at DESC",
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
        return {"id": cursor.lastrowid}


@app.patch("/api/people/{person_id}")
async def update_person(person_id: int, person: Person, x_user_id: str = Header(...)):
    """Обновить карточку."""
    data = person.dict(exclude={'fio'})
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        
        await db.execute(
            "UPDATE people SET fio = ?, data = ? WHERE id = ?",
            (person.fio, json.dumps(data, ensure_ascii=False), person_id)
        )
        await db.commit()
        return {"ok": True}


@app.delete("/api/people/{person_id}")
async def delete_person(person_id: int, x_user_id: str = Header(...)):
    """Удалить карточку."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id))
        await db.commit()
        return {"ok": True}


@app.post("/api/people/{person_id}/notes")
async def add_person_note(person_id: int, note: Note, x_user_id: str = Header(...)):
    """Добавить заметку к человеку."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        
        cursor = await db.execute(
            "INSERT INTO person_notes (person_id, text) VALUES (?, ?)", (person_id, note.text)
        )
        await db.commit()
        return {"id": cursor.lastrowid}


@app.delete("/api/people/{person_id}/notes/{note_id}")
async def delete_person_note(person_id: int, note_id: int, x_user_id: str = Header(...)):
    """Удалить заметку."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM person_notes WHERE id = ? AND person_id = ?", (note_id, person_id))
        await db.commit()
        return {"ok": True}


# === БАЗА ЗНАНИЙ ===

@app.get("/api/knowledge")
async def get_knowledge(x_user_id: str = Header(...)):
    """Получить все записи базы знаний."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM knowledge WHERE user_id = ? ORDER BY created_at DESC", (x_user_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['tags'] = json.loads(item['tags'])
            result.append(item)
        return result


@app.post("/api/knowledge")
async def create_knowledge(item: Knowledge, x_user_id: str = Header(...)):
    """Создать запись."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "INSERT INTO knowledge (user_id, title, content, tags) VALUES (?, ?, ?, ?)",
            (x_user_id, item.title, item.content, json.dumps(item.tags, ensure_ascii=False))
        )
        await db.commit()
        return {"id": cursor.lastrowid}


@app.patch("/api/knowledge/{item_id}")
async def update_knowledge(item_id: int, item: Knowledge, x_user_id: str = Header(...)):
    """Обновить запись."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM knowledge WHERE id = ? AND user_id = ?", (item_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        
        await db.execute(
            "UPDATE knowledge SET title = ?, content = ?, tags = ? WHERE id = ?",
            (item.title, item.content, json.dumps(item.tags, ensure_ascii=False), item_id)
        )
        await db.commit()
        return {"ok": True}


@app.delete("/api/knowledge/{item_id}")
async def delete_knowledge(item_id: int, x_user_id: str = Header(...)):
    """Удалить запись."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM knowledge WHERE id = ? AND user_id = ?", (item_id, x_user_id))
        await db.commit()
        return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
