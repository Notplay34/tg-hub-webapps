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


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    done: Optional[bool] = None
    person_id: Optional[int] = None
    reminder_enabled: Optional[bool] = None
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
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute(
                """INSERT INTO tasks (user_id, title, description, deadline, priority, done, person_id, reminder_enabled, reminder_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (x_user_id, task.title, task.description, task.deadline, task.priority, int(task.done), task.person_id, int(task.reminder_enabled), task.reminder_time)
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
            elif field == 'reminder_enabled':
                updates.append("reminder_enabled = ?")
                values.append(int(bool(value)))
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

import re
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_user_command(message: str, user_id: str):
    """Парсит команды пользователя напрямую, без ИИ."""
    msg_lower = message.lower().strip()
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
            
            # Убираем слова про дату из названия
            title_clean = re.sub(r'\s*(на завтра|на сегодня|на послезавтра|завтра|сегодня|срочно|важно)\s*', ' ', title).strip()
            
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
    
    # Создать контакт/карточку
    person_patterns = [
        r'создай карточку[:\s]+(.+)',
        r'добавь контакт[:\s]+(.+)',
        r'добавь человека[:\s]+(.+)',
        r'новый контакт[:\s]+(.+)',
        r'карточка[:\s]+(.+)',
    ]
    
    # Проверяем, похоже ли на ФИО с датой рождения
    # "добавь иванов иван 01.01.1990 ..."
    fio_pattern = r'добавь\s+([а-яё]+\s+[а-яё]+(?:\s+[а-яё]+)?)\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*(.*)'
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
    
    # ФИО без даты рождения (минимум 2 слова + характеристики)
    # "добавь иванов иван мама, директор, умный"
    fio_no_date = r'добавь\s+([а-яё]+\s+[а-яё]+(?:\s+[а-яё]+)?)\s+(.+)'
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
            
            # Разбиваем по запятым или пробелам
            if ',' in rest:
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
                data['role'] = ', '.join(found_roles)
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
                    """INSERT INTO tasks (user_id, title, description, deadline, priority, done)
                       VALUES (?, ?, ?, ?, ?, 0)""",
                    (user_id, title, action.get("description", ""), deadline, priority)
                )
                await db.commit()
                logger.info(f"Task created successfully!")
                return f"✅ Задача создана: {title}" + (f" (до {deadline})" if deadline else "")
            
            elif action_type == "create_person":
                fio = action.get("fio", "").strip()
                if not fio:
                    return "❌ Не указано ФИО"
                
                data = {}
                for field in ["role", "workplace", "phone", "email", "strengths", "weaknesses"]:
                    if action.get(field):
                        data[field] = action.get(field)
                
                await db.execute(
                    "INSERT INTO people (user_id, fio, data) VALUES (?, ?, ?)",
                    (user_id, fio, json.dumps(data, ensure_ascii=False))
                )
                await db.commit()
                return f"✅ Контакт добавлен: {fio}"
            
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
    
    # Сначала проверяем прямые команды (без ИИ)
    direct_command = parse_user_command(msg.message, x_user_id)
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
        
        # Загружаем историю чата (последние 20 сообщений)
        cursor = await db.execute(
            """SELECT role, content FROM chat_history 
               WHERE user_id = ? 
               ORDER BY created_at DESC LIMIT 20""",
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
Твоя задача — усиливать позиции пользователя в делах, переговорах и принятии решений.

У тебя есть ПАМЯТЬ — ты помнишь весь диалог с пользователем. Запоминай имя и всё важное!

⏰ Сейчас: {today_str} ({weekday}), {now.strftime("%H:%M")}

📊 Данные пользователя:
• Задачи ({len(active_tasks)}): {json.dumps(active_tasks, ensure_ascii=False) if active_tasks else "нет"}
• Контакты ({len(people)}): {json.dumps(people, ensure_ascii=False) if people else "нет"} 
• Знания ({len(knowledge)}): {json.dumps(knowledge, ensure_ascii=False) if knowledge else "нет"}

🎯 Ты умеешь:
- Анализировать людей, их мотивации и интересы
- Подсказывать тактики общения и переговоров
- Предупреждать о рисках и последствиях
- Думать на 2–3 шага вперёд
- Помогать с приоритетами задач

📌 Правила:
- Отвечай КРАТКО (1-3 предложения)
- Запоминай имя пользователя и контекст
- Если спрашивают "как меня зовут" — отвечай из памяти диалога
- НЕ выдумывай данных, используй только то что знаешь
- НИКОГДА не говори что создал задачу или добавил контакт — ты НЕ умеешь это делать
- Если просят создать задачу — скажи "Напиши: создай задачу [название]"
- Отвечай на русском языке
- Будь полезным советником"""

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
            max_tokens=500,
            temperature=0.7
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
