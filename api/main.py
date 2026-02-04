"""
API для TG Hub — хранение данных на сервере.
"""

import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import json
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Поддержка разных провайдеров ИИ
# Приоритет: OpenRouter > vsellm > Google > Yandex
api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("VSELM_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("YANDEX_API_KEY")

if os.getenv("OPENROUTER_API_KEY"):
    base_url = "https://openrouter.ai/api/v1"
elif os.getenv("VSELM_API_KEY"):
    base_url = os.getenv("VSELM_BASE_URL", "https://api.vsellm.ru/v1")
elif os.getenv("GOOGLE_API_KEY"):
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
else:
    base_url = None

# Для OpenRouter нужны дополнительные заголовки
default_headers = {}
if os.getenv("OPENROUTER_API_KEY"):
    default_headers = {
        "HTTP-Referer": "https://tghub.duckdns.org",
        "X-Title": "YouHub"
    }

openai_client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=120.0,  # Увеличен таймаут для бесплатных моделей
    default_headers=default_headers if default_headers else None
) if api_key and base_url else None

app = FastAPI(title="TG Hub API")

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
    person_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    done: Optional[bool] = None
    person_id: Optional[int] = None


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
    person_id: Optional[int] = None


class ChatMessage(BaseModel):
    message: str


# === База данных ===

async def init_db():
    Path("data").mkdir(exist_ok=True)
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                deadline DATE,
                priority TEXT DEFAULT 'medium',
                done INTEGER DEFAULT 0,
                person_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS person_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                tags TEXT DEFAULT '[]',
                person_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                entity_title TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Миграция: добавляем person_id если нет
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN person_id INTEGER")
        except:
            pass
        try:
            await db.execute("ALTER TABLE knowledge ADD COLUMN person_id INTEGER")
        except:
            pass
        
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()


# === УТИЛИТЫ ===

async def log_timeline(db, user_id: str, action_type: str, entity_type: str, entity_id: int, entity_title: str, details: str = ""):
    """Логирование события в timeline."""
    try:
        await db.execute(
            """INSERT INTO timeline (user_id, action_type, entity_type, entity_id, entity_title, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, action_type, entity_type, entity_id, entity_title, details)
        )
    except Exception as e:
        # Игнорируем ошибки timeline, чтобы не ломать основную функциональность
        print(f"Timeline log error: {e}")


# === ЗАДАЧИ ===

@app.get("/api/tasks")
async def get_tasks(x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
            (x_user_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]


@app.post("/api/tasks")
async def create_task(task: Task, x_user_id: str = Header(...)):
    try:
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute(
                """INSERT INTO tasks (user_id, title, description, deadline, priority, done, person_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (x_user_id, task.title, task.description, task.deadline, task.priority, int(task.done), task.person_id)
            )
            task_id = cursor.lastrowid
            await log_timeline(db, x_user_id, "created", "task", task_id, task.title)
            await db.commit()
            return {"id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания задачи: {str(e)}")


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT title, done FROM tasks WHERE id = ? AND user_id = ?", (task_id, x_user_id))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        
        old_done = row[1]
        task_title = row[0]
        
        updates = []
        values = []
        data = task.dict(exclude_unset=True)
        action_type = "updated"
        
        for field, value in data.items():
            if field == 'done':
                updates.append("done = ?")
                values.append(int(value))
                if value and not old_done:
                    action_type = "completed"
            elif value is not None or field == 'person_id':
                updates.append(f"{field} = ?")
                values.append(value)
        
        if updates:
            values.append(task_id)
            await db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
            await log_timeline(db, x_user_id, action_type, "task", task_id, task_title)
            await db.commit()
        
        return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT title FROM tasks WHERE id = ? AND user_id = ?", (task_id, x_user_id))
        row = await cursor.fetchone()
        if row:
            await log_timeline(db, x_user_id, "deleted", "task", task_id, row[0])
        await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, x_user_id))
        await db.commit()
        return {"ok": True}


# === ЛЮДИ ===

@app.get("/api/people")
async def get_people(x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM people WHERE user_id = ? ORDER BY created_at DESC", (x_user_id,))
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            person = dict(row)
            person['data'] = json.loads(person['data'])
            notes_cursor = await db.execute(
                "SELECT id, text, created_at FROM person_notes WHERE person_id = ? ORDER BY created_at DESC",
                (person['id'],)
            )
            person['notes'] = [dict(n) for n in await notes_cursor.fetchall()]
            result.append(person)
        return result


@app.post("/api/people")
async def create_person(person: Person, x_user_id: str = Header(...)):
    data = person.dict(exclude={'fio'})
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "INSERT INTO people (user_id, fio, data) VALUES (?, ?, ?)",
            (x_user_id, person.fio, json.dumps(data, ensure_ascii=False))
        )
        person_id = cursor.lastrowid
        await log_timeline(db, x_user_id, "created", "person", person_id, person.fio)
        await db.commit()
        return {"id": person_id}


@app.patch("/api/people/{person_id}")
async def update_person(person_id: int, person: Person, x_user_id: str = Header(...)):
    data = person.dict(exclude={'fio'})
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404)
        
        await db.execute(
            "UPDATE people SET fio = ?, data = ? WHERE id = ?",
            (person.fio, json.dumps(data, ensure_ascii=False), person_id)
        )
        await log_timeline(db, x_user_id, "updated", "person", person_id, person.fio)
        await db.commit()
        return {"ok": True}


@app.delete("/api/people/{person_id}")
async def delete_person(person_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT fio FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id))
        row = await cursor.fetchone()
        if row:
            await log_timeline(db, x_user_id, "deleted", "person", person_id, row[0])
        await db.execute("DELETE FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id))
        await db.commit()
        return {"ok": True}


@app.post("/api/people/{person_id}/notes")
async def add_note(person_id: int, note: Note, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT fio FROM people WHERE id = ? AND user_id = ?", (person_id, x_user_id))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        
        cursor = await db.execute("INSERT INTO person_notes (person_id, text) VALUES (?, ?)", (person_id, note.text))
        note_id = cursor.lastrowid
        await log_timeline(db, x_user_id, "note_added", "person", person_id, row[0], f"Добавлена заметка к {row[0]}")
        await db.commit()
        return {"id": note_id}


@app.delete("/api/people/{person_id}/notes/{note_id}")
async def delete_note(person_id: int, note_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM person_notes WHERE id = ? AND person_id = ?", (note_id, person_id))
        await db.commit()
        return {"ok": True}


# === БАЗА ЗНАНИЙ ===

@app.get("/api/knowledge")
async def get_knowledge(x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM knowledge WHERE user_id = ? ORDER BY created_at DESC", (x_user_id,))
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['tags'] = json.loads(item['tags'])
            result.append(item)
        return result


@app.post("/api/knowledge")
async def create_knowledge(item: Knowledge, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "INSERT INTO knowledge (user_id, title, content, tags, person_id) VALUES (?, ?, ?, ?, ?)",
            (x_user_id, item.title, item.content, json.dumps(item.tags, ensure_ascii=False), item.person_id)
        )
        item_id = cursor.lastrowid
        await log_timeline(db, x_user_id, "created", "knowledge", item_id, item.title)
        await db.commit()
        return {"id": item_id}


@app.patch("/api/knowledge/{item_id}")
async def update_knowledge(item_id: int, item: Knowledge, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id FROM knowledge WHERE id = ? AND user_id = ?", (item_id, x_user_id))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404)
        
        await db.execute(
            "UPDATE knowledge SET title = ?, content = ?, tags = ?, person_id = ? WHERE id = ?",
            (item.title, item.content, json.dumps(item.tags, ensure_ascii=False), item.person_id, item_id)
        )
        await log_timeline(db, x_user_id, "updated", "knowledge", item_id, item.title)
        await db.commit()
        return {"ok": True}


@app.delete("/api/knowledge/{item_id}")
async def delete_knowledge(item_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT title FROM knowledge WHERE id = ? AND user_id = ?", (item_id, x_user_id))
        row = await cursor.fetchone()
        if row:
            await log_timeline(db, x_user_id, "deleted", "knowledge", item_id, row[0])
        await db.execute("DELETE FROM knowledge WHERE id = ? AND user_id = ?", (item_id, x_user_id))
        await db.commit()
        return {"ok": True}


# === ИИ АССИСТЕНТ ===

@app.get("/api/timeline")
async def get_timeline(x_user_id: str = Header(...), limit: int = 50):
    """Получить timeline событий."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM timeline WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (x_user_id, limit)
        )
        return [dict(row) for row in await cursor.fetchall()]

@app.post("/api/chat")
async def chat(msg: ChatMessage, x_user_id: str = Header(...)):
    """Чат с ИИ-ассистентом, который знает все данные пользователя."""
    
    # Собираем контекст пользователя
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        
        # Задачи
        cursor = await db.execute(
            "SELECT title, description, deadline, priority, done FROM tasks WHERE user_id = ?",
            (x_user_id,)
        )
        tasks = [dict(r) for r in await cursor.fetchall()]
        
        # Люди
        cursor = await db.execute(
            "SELECT fio, data FROM people WHERE user_id = ?",
            (x_user_id,)
        )
        people = []
        for row in await cursor.fetchall():
            p = {"fio": row["fio"]}
            p.update(json.loads(row["data"]))
            people.append(p)
        
        # Знания
        cursor = await db.execute(
            "SELECT title, content, tags FROM knowledge WHERE user_id = ?",
            (x_user_id,)
        )
        knowledge = []
        for row in await cursor.fetchall():
            k = dict(row)
            k["tags"] = json.loads(k["tags"])
            knowledge.append(k)
    
    # Формируем системный промпт
    system_prompt = f"""Ты — персональный ИИ-ассистент в приложении Hub. 
Ты помогаешь пользователю управлять задачами, контактами и знаниями.

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:

📋 ЗАДАЧИ ({len(tasks)}):
{json.dumps(tasks, ensure_ascii=False, indent=2) if tasks else "Нет задач"}

👤 ЛЮДИ ({len(people)}):
{json.dumps(people, ensure_ascii=False, indent=2) if people else "Нет контактов"}

📚 БАЗА ЗНАНИЙ ({len(knowledge)}):
{json.dumps(knowledge, ensure_ascii=False, indent=2) if knowledge else "Пусто"}

ПРАВИЛА:
- Отвечай кратко и по делу
- Используй данные пользователя для персонализированных советов
- Если спрашивают о человеке — ищи в контактах
- Если спрашивают о задачах — анализируй приоритеты и дедлайны
- Отвечай на русском языке
- Будь полезным и проактивным"""

    if not openai_client:
        return {"response": "ИИ не настроен. Установите VSELM_API_KEY, GOOGLE_API_KEY или YANDEX_API_KEY в .env"}
    
    try:
        # Определяем модель в зависимости от провайдера
        model = os.getenv("AI_MODEL", "gpt-3.5-turbo")  # Можно переопределить через .env
        
        if "openrouter.ai" in base_url:
            # Бесплатные модели OpenRouter
            model = os.getenv("AI_MODEL", "google/gemma-3-4b-it:free")  # Быстрая бесплатная модель
        elif "vsellm.ru" in base_url:
            model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
        elif "google" in base_url.lower():
            model = os.getenv("AI_MODEL", "gemini-pro")
        
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg.message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        return {"response": response.choices[0].message.content}
    
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return {"response": "Ошибка доступа к ИИ. Проверьте API ключ и доступность сервиса из России."}
        elif "429" in error_msg or "quota" in error_msg.lower():
            return {"response": "Лимит запросов исчерпан. Попробуйте позже или используйте другой API."}
        return {"response": f"Ошибка ИИ: {error_msg}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
