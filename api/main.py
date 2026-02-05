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
    reminder_enabled: bool = False
    reminder_time: Optional[str] = None
    recurrence_type: str = "none"  # none, daily, weekly, monthly


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    done: Optional[bool] = None
    person_id: Optional[int] = None
    reminder_enabled: Optional[bool] = None
    reminder_time: Optional[str] = None
    recurrence_type: Optional[str] = None
    reminder_time: Optional[str] = None


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
                reminder_enabled INTEGER DEFAULT 0,
                reminder_time TEXT,
                recurrence_type TEXT DEFAULT 'none',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Добавляем колонки если их нет (для существующих БД)
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN reminder_enabled INTEGER DEFAULT 0")
        except:
            pass
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN reminder_time TEXT")
        except:
            pass
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN recurrence_type TEXT DEFAULT 'none'")
        except:
            pass
        
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
        
        # История чата для памяти ИИ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id, created_at DESC)")
        
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
        # Валидация: повторяющиеся задачи без дедлайна запрещаем
        if task.recurrence_type and task.recurrence_type != "none" and not task.deadline:
            raise HTTPException(
                status_code=400,
                detail="Для повторяющейся задачи нужно указать дедлайн.",
            )
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute(
                """INSERT INTO tasks (user_id, title, description, deadline, priority, done, person_id, reminder_enabled, reminder_time, recurrence_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    x_user_id,
                    task.title,
                    task.description,
                    task.deadline,
                    task.priority,
                    int(task.done),
                    task.person_id,
                    int(task.reminder_enabled),
                    task.reminder_time,
                    task.recurrence_type or "none",
                )
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
        cursor = await db.execute(
            """
            SELECT title, description, deadline, priority, done, person_id,
                   reminder_enabled, reminder_time, recurrence_type
            FROM tasks
            WHERE id = ? AND user_id = ?
            """,
            (task_id, x_user_id)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        
        # Текущее состояние до обновления
        cur_title = row[0]
        cur_description = row[1]
        cur_deadline = row[2]
        cur_priority = row[3]
        old_done = row[4]
        cur_person_id = row[5]
        cur_reminder_enabled = row[6]
        cur_reminder_time = row[7]
        cur_recurrence_type = row[8] or "none"
        
        updates: list[str] = []
        values = []
        data = task.dict(exclude_unset=True)
        action_type = "updated"
        
        # Валидация: если меняем recurrence_type, но после обновления у задачи не будет дедлайна — ошибка
        if "recurrence_type" in data:
            new_recur = data["recurrence_type"] or "none"
            new_deadline = data.get("deadline", cur_deadline)
            if new_recur != "none" and not new_deadline:
                raise HTTPException(
                    status_code=400,
                    detail="Для повторяющейся задачи нужно указать дедлайн.",
                )
        
        for field, value in data.items():
            if field == "done":
                updates.append("done = ?")
                values.append(int(value))
                if value and not old_done:
                    action_type = "completed"
            elif field == "title":
                updates.append("title = ?")
                values.append(value)
                cur_title = value
            elif field == "description":
                updates.append("description = ?")
                values.append(value)
                cur_description = value
            elif field == "deadline":
                updates.append("deadline = ?")
                values.append(value)
                cur_deadline = value
            elif field == "priority":
                updates.append("priority = ?")
                values.append(value)
                cur_priority = value
            elif field == "person_id":
                updates.append("person_id = ?")
                values.append(value)
                cur_person_id = value
            elif field == "reminder_enabled":
                updates.append("reminder_enabled = ?")
                values.append(int(bool(value)))
                cur_reminder_enabled = int(bool(value))
            elif field == "reminder_time":
                updates.append("reminder_time = ?")
                values.append(value)
                cur_reminder_time = value
            elif field == "recurrence_type":
                updates.append("recurrence_type = ?")
                values.append(value or "none")
                cur_recurrence_type = value or "none"
        
        if updates:
            values.append(task_id)
            await db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
            await log_timeline(db, x_user_id, action_type, "task", task_id, cur_title)
            
            # Если задача только что была завершена и у неё есть повторение — создаём следующую
            if "done" in data and data["done"] and not old_done and cur_deadline and cur_recurrence_type != "none":
                try:
                    from datetime import date
                    import calendar
                    
                    d = date.fromisoformat(cur_deadline)
                    if cur_recurrence_type == "daily":
                        new_date = d + timedelta(days=1)
                    elif cur_recurrence_type == "weekly":
                        new_date = d + timedelta(weeks=1)
                    elif cur_recurrence_type == "monthly":
                        year = d.year
                        month = d.month + 1
                        if month > 12:
                            month = 1
                            year += 1
                        # безопасно подбираем день
                        last_day = calendar.monthrange(year, month)[1]
                        day = min(d.day, last_day)
                        new_date = date(year, month, day)
                    else:
                        new_date = None
                    
                    if new_date:
                        await db.execute(
                            """
                            INSERT INTO tasks (
                                user_id, title, description, deadline, priority,
                                done, person_id, reminder_enabled, reminder_time, recurrence_type
                            )
                            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                            """,
                            (
                                x_user_id,
                                cur_title,
                                cur_description,
                                new_date.isoformat(),
                                cur_priority,
                                cur_person_id,
                                cur_reminder_enabled,
                                cur_reminder_time,
                                cur_recurrence_type,
                            )
                        )
                except Exception as e:
                    # Логируем, но не ломаем основной запрос
                    import logging
                    logging.getLogger(__name__).error(f"Failed to create recurring task: {e}")
            
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

import re
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_user_command(message: str, user_id: str):
    """Парсит команды пользователя напрямую, без ИИ."""
    # Очищаем от лишнего шума: эмодзи, повторяющихся пробелов
    # Оригинал используем для логирования при необходимости
    msg_lower = message.lower().strip()
    # Убираем простые эмодзи и лишние символы, чтобы не попадали в заголовки задач
    msg_lower = re.sub(r'[^\w\s\.\,\-\:\;\!\?ёа-я0-9]', ' ', msg_lower)
    msg_lower = re.sub(r'\s+', ' ', msg_lower).strip()
    logger.info(f"Parsing message: {msg_lower}")
    
    # Создать задачу
    create_patterns = [
        r'создай задачу[:\s]+(.+)',
        r'добавь задачу[:\s]+(.+)',
        r'напомни[:\s]*[,:]?\s*(.+)',
        r'задача[:\s]+(.+)',
        r'нужно\s+(.+)',
        r'надо\s+(.+)',
        r'не забыть\s+(.+)',
        r'купить\s+(.+)',
        # Глаголы-инфинитивы в начале (позвонить, сделать, разобраться...)
        r'^((?:по)?звонить\s+.+)',
        r'^(сделать\s+.+)',
        r'^(разобраться\s+.+)',
        r'^(написать\s+.+)',
        r'^(отправить\s+.+)',
        r'^(проверить\s+.+)',
        r'^(подготовить\s+.+)',
        r'^(встретиться\s+.+)',
        r'^(забрать\s+.+)',
        r'^(оплатить\s+.+)',
        r'^(заказать\s+.+)',
        r'^(записаться\s+.+)',
    ]
    
    for pattern in create_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            logger.info(f"Pattern matched: {pattern} -> {match.group(1)}")
            title = match.group(1).strip()
            
            # Ищем дату в формате DD.MM или DD.MM.YYYY
            date_match = re.search(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?', title)
            deadline = None
            
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
                try:
                    deadline = datetime(year, month, day).date().isoformat()
                    # Убираем дату из названия
                    title = re.sub(r'\s*\d{1,2}\.\d{1,2}(?:\.\d{4})?\s*', ' ', title).strip()
                except ValueError:
                    pass
            
            # Если дата не найдена - проверяем слова
            if not deadline:
                if 'завтра' in msg_lower or 'на завтра' in msg_lower:
                    deadline = (datetime.now().date() + timedelta(days=1)).isoformat()
                elif 'послезавтра' in msg_lower:
                    deadline = (datetime.now().date() + timedelta(days=2)).isoformat()
                else:
                    # Проверяем дни недели
                    weekdays = {
                        'понедельник': 0, 'пн': 0,
                        'вторник': 1, 'вт': 1,
                        'среда': 2, 'среду': 2, 'ср': 2,
                        'четверг': 3, 'чт': 3,
                        'пятница': 4, 'пятницу': 4, 'пт': 4,
                        'суббота': 5, 'субботу': 5, 'сб': 5,
                        'воскресенье': 6, 'воскресение': 6, 'вс': 6,
                    }
                    
                    found_weekday = None
                    found_day_name = None
                    for day_name, day_num in weekdays.items():
                        if day_name in msg_lower:
                            found_weekday = day_num
                            found_day_name = day_name
                            break
                    
                    if found_weekday is not None:
                        today = datetime.now().date()
                        current_weekday = today.weekday()
                        days_ahead = found_weekday - current_weekday
                        if days_ahead <= 0:  # Если день уже прошёл или сегодня - следующая неделя
                            days_ahead += 7
                        deadline = (today + timedelta(days=days_ahead)).isoformat()
                        # Убираем день недели из названия
                        title = re.sub(rf'\s*(на\s+|в\s+)?{found_day_name}\s*', ' ', title, flags=re.IGNORECASE).strip()
                    else:
                        # По умолчанию - сегодня
                        deadline = datetime.now().date().isoformat()
            
            # Убираем слова про дату и служебные слова из названия
            title_clean = re.sub(
                r'\b(на завтра|на сегодня|на послезавтра|завтра|сегодня|срочно|важно|пожалуйста|плиз|плииз)\b',
                ' ',
                title,
                flags=re.IGNORECASE,
            ).strip()
            # Если после чистки заголовок слишком длинный — обрежем
            if len(title_clean) > 120:
                title_clean = title_clean[:117].rstrip() + '...'
            
            priority = "medium"
            if 'срочно' in msg_lower or 'важно' in msg_lower:
                priority = "high"
            
            return {
                "action": "create_task",
                "title": title_clean.capitalize() if title_clean else title.capitalize(),
                "deadline": deadline,
                "priority": priority
            }
    
    # Отметить выполненной
    done_patterns = [
        r'выполн(?:ено|ил|ена)[:\s]+(.+)',
        r'сделан[оа]?[:\s]+(.+)',
        r'готово[:\s]+(.+)',
        r'закрой задачу[:\s]+(.+)',
    ]
    
    for pattern in done_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            return {
                "action": "complete_task",
                "title": match.group(1).strip()
            }
    
    # Создать контакт/карточку (явные фразы)
    person_patterns = [
        r'создай карточку[:\s]+(.+)',
        r'создай контакт[:\s]+(.+)',
        r'добавь контакт[:\s]+(.+)',
        r'добавь человека[:\s]+(.+)',
        r'добавь карточку[:\s]+(.+)',
        r'новый контакт[:\s]+(.+)',
        r'запиши контакт[:\s]+(.+)',
        r'карточка[:\s]+(.+)',
    ]
    
    # Проверяем, похоже ли на ФИО с датой рождения (2–4 слова: Фамилия Имя Отчество)
    # "добавь иванов иван иванович 01.01.1990 ..."
    fio_pattern = r'добавь\s+([а-яё]+\s+[а-яё]+(?:\s+[а-яё]+){0,2})\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*(.*)'
    fio_match = re.search(fio_pattern, msg_lower)
    if fio_match:
        fio = fio_match.group(1).strip()
        birth_str = fio_match.group(2)
        rest = fio_match.group(3).strip()
        
        # Конвертируем дату
        try:
            d, m, y = birth_str.split('.')
            birth_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        except:
            birth_date = None
        
        data = {}
        if birth_date:
            data['birth_date'] = birth_date
        
        # Парсим характеристики
        if rest:
            chars = re.split(r'[,\s]+', rest)
            chars = [c.strip() for c in chars if c.strip()]
            if chars:
                data['strengths'] = ', '.join(chars)
        
        logger.info(f"FIO pattern with date: {fio}, birth: {birth_date}")
        
        return {
            "action": "create_person",
            "fio": fio.title(),
            **data
        }
    
    # ФИО без даты (2–4 слова + роль/характеристики)
    # "добавь иванов иван мама, директор" или "добавь албегова наталья сергеевна мама, компаньон"
    fio_no_date = r'добавь\s+([а-яё]+\s+[а-яё]+(?:\s+[а-яё]+){0,2})\s+(.+)'
    fio_match2 = re.search(fio_no_date, msg_lower)
    if fio_match2:
        fio = fio_match2.group(1).strip()
        rest = fio_match2.group(2).strip()
        
        # Проверяем что это не задача
        task_words = ['купить', 'позвонить', 'сделать', 'проверить', 'написать', 'отправить', 'забрать', 'оплатить']
        if any(word in fio.lower() for word in task_words):
            pass  # Это задача, не контакт
        else:
            data = {}
            
            # Списки для распределения
            roles = ['мама', 'папа', 'отец', 'мать', 'брат', 'сестра', 'муж', 'жена', 'сын', 'дочь',
                     'дядя', 'тётя', 'тетя', 'дед', 'бабушка', 'друг', 'подруга', 'коллега', 
                     'партнер', 'партнёр', 'начальник', 'директор', 'менеджер', 'клиент', 
                     'заказчик', 'поставщик', 'инвестор', 'компаньон', 'сосед', 'знакомый']
            
            weaknesses_words = ['забывчивый', 'забывчива', 'вспыльчивый', 'вспыльчива', 
                               'ленивый', 'ленива', 'жадный', 'жадная', 'нервный', 'нервная',
                               'непунктуальный', 'непунктуальна', 'необязательный', 'необязательна']
            
            # Разбиваем по запятым (блоки смысла)
            if ',' in rest or ';' in rest:
                words = [w.strip() for w in re.split(r'[,;]', rest) if w.strip()]
            else:
                words = rest.split()
            
            found_roles = []
            strengths = []
            weaknesses = []
            
            for word in words:
                word_lower = word.lower()
                if word_lower in roles:
                    found_roles.append(word)
                elif word_lower in weaknesses_words:
                    weaknesses.append(word)
                elif any(w in word_lower for w in ['партнер', 'бизнес', 'работ']):
                    found_roles.append(word)
                else:
                    strengths.append(word)
            
            if found_roles:
                data['relation'] = ', '.join(found_roles)
            if strengths:
                data['strengths'] = ', '.join(strengths)
            if weaknesses:
                data['weaknesses'] = ', '.join(weaknesses)
            
            logger.info(f"FIO pattern without date: {fio}, data: {data}")
            
            return {
                "action": "create_person",
                "fio": fio.title(),
                **data
            }
    
    for pattern in person_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            text = match.group(1).strip()
            # Парсим данные из текста
            # Формат: ФИО [дата] [роль], [характеристики]
            
            parts = re.split(r'[,;]', text)
            fio = parts[0].strip()
            
            # Ищем дату рождения в ФИО (DD.MM.YYYY)
            birth_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', fio)
            birth_date = None
            if birth_match:
                birth_date = birth_match.group(1)
                # Конвертируем в YYYY-MM-DD
                try:
                    d, m, y = birth_date.split('.')
                    birth_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except:
                    birth_date = None
                fio = re.sub(r'\s*\d{1,2}\.\d{1,2}\.\d{4}\s*', ' ', fio).strip()
            
            # Остальные части - характеристики
            data = {}
            if birth_date:
                data['birth_date'] = birth_date
            
            if len(parts) > 1:
                # Первая часть после ФИО - роль
                role = parts[1].strip()
                if role:
                    data['role'] = role
                
                # Остальное - в strengths или notes
                if len(parts) > 2:
                    characteristics = ', '.join(p.strip() for p in parts[2:] if p.strip())
                    if characteristics:
                        data['strengths'] = characteristics
            
            logger.info(f"Creating person: {fio}, data: {data}")
            
            return {
                "action": "create_person",
                "fio": fio.title(),
                **data
            }
    
    # Обновление контакта: "обнови контакт Удалов..., сделай его партнёром по бизнесу"
    update_pattern = r'обнови контакт\s+(.+?)\s*(?:,|–|-)\s*(.+)'
    m_update = re.search(update_pattern, msg_lower)
    if m_update:
        fio_query = m_update.group(1).strip()
        rest = m_update.group(2).strip()
        data = {}
        # Пытаемся распознать роль и характеристики аналогично созданию
        roles = ['мама', 'папа', 'отец', 'мать', 'брат', 'сестра', 'муж', 'жена', 'сын', 'дочь',
                 'дядя', 'тётя', 'тетя', 'дед', 'бабушка', 'друг', 'подруга', 'коллега', 
                 'партнер', 'партнёр', 'начальник', 'директор', 'менеджер', 'клиент', 
                 'заказчик', 'поставщик', 'инвестор', 'компаньон', 'сосед', 'знакомый']
        weaknesses_words = ['забывчивый', 'забывчива', 'вспыльчивый', 'вспыльчива', 
                           'ленивый', 'ленива', 'жадный', 'жадная', 'нервный', 'нервная',
                           'непунктуальный', 'непунктуальна', 'необязательный', 'необязательна']
        parts = [w.strip() for w in re.split(r'[,;]', rest) if w.strip()]
        found_roles = []
        strengths = []
        weaknesses = []
        for part in parts:
            wl = part.lower()
            if wl in roles or any(w in wl for w in ['партнер', 'бизнес', 'работ']):
                found_roles.append(part)
            elif wl in weaknesses_words:
                weaknesses.append(part)
            else:
                strengths.append(part)
        if found_roles:
            data['relation'] = ', '.join(found_roles)
        if strengths:
            data['strengths'] = ', '.join(strengths)
        if weaknesses:
            data['weaknesses'] = ', '.join(weaknesses)
        
        return {
            "action": "update_person",
            "fio_query": fio_query,
            **data
        }
    
    return None


def parse_relative_date(text: str) -> str:
    """Преобразует относительные даты в формат YYYY-MM-DD."""
    today = datetime.now().date()
    text_lower = text.lower()
    
    if 'сегодня' in text_lower:
        return today.isoformat()
    elif 'завтра' in text_lower:
        return (today + timedelta(days=1)).isoformat()
    elif 'послезавтра' in text_lower:
        return (today + timedelta(days=2)).isoformat()
    elif 'через неделю' in text_lower:
        return (today + timedelta(weeks=1)).isoformat()
    elif 'через месяц' in text_lower:
        return (today + timedelta(days=30)).isoformat()
    
    # Пытаемся найти дату в формате DD.MM или DD.MM.YYYY
    date_match = re.search(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?', text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else today.year
        try:
            return datetime(year, month, day).date().isoformat()
        except:
            pass
    
    return None


async def execute_ai_action(action: dict, user_id: str) -> str:
    """Выполняет действие от ИИ и возвращает результат."""
    action_type = action.get("action")
    logger.info(f"Executing action: {action_type} for user {user_id}")
    logger.info(f"Action data: {action}")
    
    try:
        async with aiosqlite.connect(DATABASE) as db:
            if action_type == "create_task":
                title = action.get("title", "").strip()
                if not title:
                    return "❌ Не указано название задачи"
                
                deadline = action.get("deadline")
                if deadline and not re.match(r'\d{4}-\d{2}-\d{2}', deadline):
                    deadline = parse_relative_date(deadline)
                
                priority = action.get("priority", "medium")
                if priority not in ["low", "medium", "high"]:
                    priority = "medium"
                
                logger.info(f"Creating task: {title}, deadline: {deadline}, user: {user_id}")
                
                await db.execute(
                    """INSERT INTO tasks (user_id, title, description, deadline, priority, done, person_id, reminder_enabled, reminder_time, recurrence_type)
                       VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 'none')""",
                    (user_id, title, action.get("description", ""), deadline, priority)
                )
                await db.commit()
                logger.info(f"Task created successfully!")
                return f"✅ Задача создана: {title}" + (f" (до {deadline})" if deadline else "")
            
            elif action_type == "create_person":
                fio = action.get("fio", "").strip()
                if not fio:
                    return "❌ Не указано ФИО"
                
                # Поля карточки: relation (кем приходится), birth_date, workplace, strengths, weaknesses и т.д.
                data = {}
                relation = action.get("relation") or action.get("role")
                if relation:
                    data["relation"] = relation
                for field in ["birth_date", "workplace", "phone", "email", "financial",
                             "strengths", "weaknesses", "benefits", "problems"]:
                    if action.get(field):
                        data[field] = action.get(field)
                
                await db.execute(
                    "INSERT INTO people (user_id, fio, data) VALUES (?, ?, ?)",
                    (user_id, fio, json.dumps(data, ensure_ascii=False))
                )
                await db.commit()
                
                summary_parts = []
                if data.get("relation"):
                    summary_parts.append(f"кем приходится: {data['relation']}")
                if data.get("strengths"):
                    summary_parts.append(f"сильные стороны: {data['strengths']}")
                if data.get("weaknesses"):
                    summary_parts.append(f"слабые стороны: {data['weaknesses']}")
                summary = "; ".join(summary_parts) if summary_parts else ""
                if summary:
                    return f"✅ Контакт добавлен: {fio} ({summary})"
                return f"✅ Контакт добавлен: {fio}"
            
            elif action_type == "update_person":
                fio_query = (action.get("fio_query") or "").strip()
                if not fio_query:
                    return "❌ Не указано, кого обновлять"
                
                cursor = await db.execute(
                    "SELECT id, fio, data FROM people WHERE user_id = ? AND LOWER(fio) LIKE ? LIMIT 1",
                    (user_id, f"%{fio_query.lower()}%")
                )
                row = await cursor.fetchone()
                if not row:
                    return f"❌ Контакт не найден по запросу: {fio_query}"
                
                person_id = row[0]
                fio = row[1]
                try:
                    data = json.loads(row[2]) if row[2] else {}
                except Exception:
                    data = {}
                
                for field in ["relation", "workplace", "financial", "strengths", "weaknesses", "benefits", "problems"]:
                    if action.get(field):
                        data[field] = action.get(field)
                
                await db.execute(
                    "UPDATE people SET data = ? WHERE id = ?",
                    (json.dumps(data, ensure_ascii=False), person_id)
                )
                await db.commit()
                
                summary_parts = []
                if action.get("relation"):
                    summary_parts.append(f"кем приходится: {action['relation']}")
                if action.get("strengths"):
                    summary_parts.append(f"сильные стороны: {action['strengths']}")
                if action.get("weaknesses"):
                    summary_parts.append(f"слабые стороны: {action['weaknesses']}")
                summary = "; ".join(summary_parts) if summary_parts else ""
                if summary:
                    return f"✅ Контакт обновлён: {fio} ({summary})"
                return f"✅ Контакт обновлён: {fio}"
            
            elif action_type == "create_knowledge":
                title = action.get("title", "").strip()
                if not title:
                    return "❌ Не указан заголовок"
                
                await db.execute(
                    "INSERT INTO knowledge (user_id, title, content, tags) VALUES (?, ?, ?, ?)",
                    (user_id, title, action.get("content", ""), json.dumps(action.get("tags", []), ensure_ascii=False))
                )
                await db.commit()
                return f"✅ Запись добавлена: {title}"
            
            elif action_type == "complete_task":
                title = action.get("title", "").strip().lower()
                if not title:
                    return "❌ Не указана задача"
                
                cursor = await db.execute(
                    "SELECT id, title FROM tasks WHERE user_id = ? AND done = 0",
                    (user_id,)
                )
                tasks = await cursor.fetchall()
                
                for task in tasks:
                    if title in task[1].lower():
                        await db.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task[0],))
                        await db.commit()
                        return f"✅ Задача выполнена: {task[1]}"
                
                return "❌ Задача не найдена"
        
        return "❌ Неизвестное действие"
    
    except Exception as e:
        logger.error(f"Error executing action: {e}")
        return f"❌ Ошибка: {str(e)}"


@app.post("/api/chat")
async def chat(msg: ChatMessage, x_user_id: str = Header(...)):
    """Чат с ИИ-ассистентом, который знает все данные пользователя."""
    
    text_raw = msg.message.strip()
    text_lower = text_raw.lower()

    # --- Управление памятью диалога через команды ---
    # Новый диалог / очистка истории
    if text_lower in ("новый диалог", "очистить диалог", "очисти диалог", "reset", "start over"):
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute("DELETE FROM chat_history WHERE user_id = ?", (x_user_id,))
            await db.commit()
        return {
            "response": "Я очистил нашу историю. Можем начать заново с чистого листа.",
            "action_executed": False,
        }

    # Забудь про X — удаляем сообщения, где встречается фраза
    forget_match = re.match(r"забудь про (.+)", text_lower)
    if forget_match:
        phrase = forget_match.group(1).strip()
        async with aiosqlite.connect(DATABASE) as db:
            like = f"%{phrase}%"
            await db.execute(
                "DELETE FROM chat_history WHERE user_id = ? AND LOWER(content) LIKE ?",
                (x_user_id, like),
            )
            await db.commit()
        return {
            "response": f"Ок, постараюсь больше не учитывать информацию про «{phrase}».",
            "action_executed": False,
        }

    # Сначала проверяем прямые команды (без ИИ)
    direct_command = parse_user_command(text_raw, x_user_id)
    if direct_command:
        result = await execute_ai_action(direct_command, x_user_id)
        logger.info(f"Direct command executed: {direct_command['action']} -> {result}")
        
        # Сохраняем в историю
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (x_user_id, "user", msg.message)
            )
            await db.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (x_user_id, "assistant", result)
            )
            await db.commit()
        
        return {"response": result, "action_executed": True}
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        
        # Задачи (только активные для краткости)
        cursor = await db.execute(
            "SELECT id, title, description, deadline, priority, done FROM tasks WHERE user_id = ?",
            (x_user_id,)
        )
        tasks = [dict(r) for r in await cursor.fetchall()]
        active_tasks = [t for t in tasks if not t["done"]]
        
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
        
        # Загружаем историю чата (последние 30 сообщений)
        cursor = await db.execute(
            """SELECT role, content FROM chat_history 
               WHERE user_id = ? 
               ORDER BY created_at DESC LIMIT 30""",
            (x_user_id,)
        )
        history_rows = await cursor.fetchall()
        chat_history = [{"role": row["role"], "content": row["content"]} for row in reversed(history_rows)]
    
    # Текущая дата и время
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")
    weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
    
    # Формируем системный промпт
    system_prompt = f"""Ты — стратегический ИИ-ассистент YouHub.
Твоя задача — усиливать позиции пользователя в делах, переговорах и долгосрочных решениях.

У тебя есть ПАМЯТЬ — ты помнишь весь диалог с пользователем. Запоминай имя и всё важное.

⏰ Сейчас: {today_str} ({weekday}), {now.strftime("%H:%M")}

📊 Данные пользователя:
• Задачи ({len(active_tasks)}): {json.dumps(active_tasks, ensure_ascii=False) if active_tasks else "нет"}
• Контакты ({len(people)}): {json.dumps(people, ensure_ascii=False) if people else "нет"} 
• Знания ({len(knowledge)}): {json.dumps(knowledge, ensure_ascii=False) if knowledge else "нет"}

🎯 Формат ответа (всегда):
1) Краткий вывод (1–2 предложения).
2) 1–3 конкретных шага / формулировки для действий.
3) Если есть важные риски — 1 короткое предупреждение.

🧠 Когда вопрос про ЛЮДЕЙ:
- Анализируй интересы, мотивацию, рычаги влияния и возможные сценарии.
- Предлагай фразы и тактики общения (как сказать, чтобы было выгодно пользователю).
- Отмечай возможные конфликты и скрытые последствия.

📋 Когда вопрос про ЗАДАЧИ и дела:
- Помогай расставить приоритеты и отсечь лишнее.
- Строй план действий на 2–3 шага вперёд, с минимальными затратами.

📌 Правила:
- Пиши КРАТКО: без воды, без морализаторства, максимум пользы.
- Запоминай имя пользователя и контекст диалога.
- Если спрашивают "как меня зовут" — отвечай из памяти диалога.
- НЕ выдумывай факты, опирайся только на данные пользователя и логический вывод.
- НИКОГДА не говори, что создал задачу или добавил контакт — ты этого не умеешь.
- Если просят создать задачу — скажи: "Напиши: создай задачу …", без имитации действия.
- Отвечай только на русском языке.
- Думай как советник из тени, но действуй этично и в интересах пользователя."""

    if not openai_client:
        return {"response": "ИИ не настроен. Установите OPENROUTER_API_KEY в .env"}
    
    try:
        model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
        if base_url and "openrouter.ai" in base_url:
            model = os.getenv("AI_MODEL", "google/gemma-3-4b-it:free")
        elif base_url and "vsellm.ru" in base_url:
            model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
        elif base_url and "google" in base_url.lower():
            model = os.getenv("AI_MODEL", "gemini-pro")
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": msg.message})
        
        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=400,
            temperature=0.4
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Сохраняем в историю
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (x_user_id, "user", msg.message)
            )
            await db.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (x_user_id, "assistant", ai_response)
            )
            await db.execute(
                """DELETE FROM chat_history WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50
                )""",
                (x_user_id, x_user_id)
            )
            await db.commit()
        
        return {"response": ai_response, "action_executed": False}
    
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return {"response": "Ошибка доступа к ИИ. Проверьте API ключ."}
        elif "429" in error_msg or "quota" in error_msg.lower():
            return {"response": "Лимит запросов исчерпан. Попробуйте позже."}
        return {"response": f"Ошибка ИИ: {error_msg}"}


@app.delete("/api/chat/history")
async def clear_chat_history(x_user_id: str = Header(...)):
    """Очистить историю чата."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM chat_history WHERE user_id = ?", (x_user_id,))
        await db.commit()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
