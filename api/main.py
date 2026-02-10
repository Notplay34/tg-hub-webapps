"""
API для TG Hub — хранение данных на сервере.
"""

import os
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Память чата
CHAT_HISTORY_LIMIT = 80          # сколько последних сообщений держим "сырыми"
CHAT_CONTEXT_MESSAGES = 24       # сколько последних сообщений отправляем в ИИ (меньше = быстрее, без старых фактов)
CHAT_SUMMARY_CHUNK = 40          # сколько старых сообщений сжимаем за один раз
CHAT_SUMMARY_THRESHOLD = 200     # с какого общего количества начинаем сжатие

"""
Импортируем AI‑клиент и репозиторий истории чата.
Используем try/except, чтобы код работал и при запуске как пакета (`api.main`),
и при прямом запуске `python api/main.py`.
"""
try:
    from api.services.ai_client import (
        chat as ai_chat,
        is_ai_configured,
        AiNotConfiguredError,
    )
    from api.repositories import chat_history as chat_repo
    from api.agent_core import AgentCore
except ImportError:  # fallback для запуска из каталога api
    from services.ai_client import (  # type: ignore[no-redef]
        chat as ai_chat,
        is_ai_configured,
        AiNotConfiguredError,
    )
    from repositories import chat_history as chat_repo  # type: ignore[no-redef]
    from agent_core import AgentCore  # type: ignore[no-redef]

app = FastAPI(title="TG Hub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE = "data/hub.db"

# Agent Core — единый экземпляр для работы с состоянием агента
agent_core = AgentCore(DATABASE)


async def extract_person_with_ai(text: str):
    """
    Извлекает данные контакта из произвольной фразы через ИИ.
    Возвращает dict с ключами fio, relation, birth_date, strengths, weaknesses или None при ошибке.
    """
    prompt = """Из строки пользователя извлеки данные контакта (карточки человека).
Верни ТОЛЬКО валидный JSON без markdown и комментариев, с ключами:
- fio: полное ФИО (Фамилия Имя Отчество), одна строка
- relation: кем приходится (сын, дочь, супруга, коллега и т.д.) или пустая строка
- birth_date: дата рождения в формате YYYY-MM-DD или null
- strengths: сильные стороны / положительные черты, одна строка
- weaknesses: слабые стороны / отрицательные черты, одна строка

Примеры:
"Кудрявский Сергей Игоревич, сын, 02.09.2020, вредный, очень милый" -> {"fio": "Кудрявский Сергей Игоревич", "relation": "сын", "birth_date": "2020-09-02", "strengths": "очень милый", "weaknesses": "вредный"}
"Иванов Иван, коллега" -> {"fio": "Иванов Иван", "relation": "коллега", "birth_date": null, "strengths": "", "weaknesses": ""}

Строка пользователя:
"""
    try:
        response = await ai_chat(
            [{"role": "user", "content": prompt + text.strip()}],
            model_hint="chat",
            max_tokens=300,
            temperature=0.1,
        )
        # Убрать возможную обёртку в ```json
        raw = response.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        data = json.loads(raw)
        if not isinstance(data.get("fio"), str) or not data["fio"].strip():
            return None
        # Нормализуем ключи и пустые значения
        result = {"fio": data["fio"].strip().title()}
        for key in ("relation", "birth_date", "strengths", "weaknesses"):
            val = data.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            result[key] = val.strip() if isinstance(val, str) else val
        return result
    except (json.JSONDecodeError, AiNotConfiguredError, Exception) as e:
        logger.warning("extract_person_with_ai failed: %s", e)
        return None


async def extract_command_with_ai(message: str):
    """
    Понимает намерение по сырому тексту и возвращает команду для execute_ai_action,
    либо None (вопрос, болтовня, неясно). Используется когда parse_user_command не сработал.
    """
    import re as _re
    prompt = """Определи намерение пользователя по сообщению. Варианты:
- task — добавить задачу (нужны: title; опционально deadline в YYYY-MM-DD)
- expense — учёт расхода (нужны: amount — число; опционально category)
- income — учёт дохода (нужны: amount; опционально category)
- goal — финансовая цель (нужны: title, target_amount — число)
- contact — добавить контакта/карточку человека (нужны: fio; опционально relation, birth_date YYYY-MM-DD)
- note — заметка в базу знаний (нужны: content)

Суммы всегда числами: 200000 для "200 тысяч", 500 для "500 руб".
Если это вопрос, приветствие, непонятно или не подходит ни один тип — верни intent: "none".

Ответь ОДНОЙ строкой JSON без markdown. Примеры:
"хочу накопить на отпуск 200 тысяч" -> {"intent":"goal","title":"отпуск","target_amount":200000}
"потратил 500 на обед" -> {"intent":"expense","amount":500,"category":"еда"}
"напомни завтра позвонить маме" -> {"intent":"task","title":"позвонить маме","deadline":"завтра"}
"просто спросил" -> {"intent":"none"}

Сообщение пользователя:
"""
    try:
        response = await ai_chat(
            [{"role": "user", "content": prompt + message.strip()[:500]}],
            model_hint="chat",
            max_tokens=250,
            temperature=0.1,
        )
        raw = response.strip()
        if raw.startswith("```"):
            raw = _re.sub(r"^```\w*\n?", "", raw)
            raw = _re.sub(r"\n?```\s*$", "", raw)
        data = json.loads(raw)
        intent = (data.get("intent") or "none").strip().lower()
        if intent == "none":
            return None

        today = datetime.now().date().isoformat()

        if intent == "task":
            title = (data.get("title") or "").strip()
            if not title:
                return None
            deadline = (data.get("deadline") or "").strip()
            if deadline and not _re.match(r"\d{4}-\d{2}-\d{2}", deadline):
                deadline = parse_relative_date(deadline) or None
            return {"action": "create_task", "title": title, "deadline": deadline or None, "description": ""}

        if intent == "expense":
            try:
                amount = float(data.get("amount", 0))
            except (TypeError, ValueError):
                return None
            if amount <= 0:
                return None
            category = (data.get("category") or "Разное").strip()[:100]
            return {"action": "add_finance_transaction", "type": "expense", "amount": amount, "category": category, "date": today}

        if intent == "income":
            try:
                amount = float(data.get("amount", 0))
            except (TypeError, ValueError):
                return None
            if amount <= 0:
                return None
            category = (data.get("category") or "Доход").strip()[:100]
            return {"action": "add_finance_transaction", "type": "income", "amount": amount, "category": category, "date": today}

        if intent == "goal":
            title = (data.get("title") or "").strip()[:200]
            if not title:
                return None
            try:
                target = float(data.get("target_amount", 0))
            except (TypeError, ValueError):
                return None
            if target <= 0:
                return None
            return {"action": "add_finance_goal", "title": title, "target_amount": target}

        if intent == "contact":
            fio = (data.get("fio") or "").strip().title()
            if not fio:
                return None
            out = {"action": "create_person", "fio": fio}
            for key in ("relation", "birth_date", "strengths", "weaknesses"):
                if data.get(key):
                    out[key] = data[key] if isinstance(data[key], str) else str(data[key])
            return out

        if intent == "note":
            content = (data.get("content") or "").strip()[:500]
            if not content:
                return None
            title = content[:150] + ("..." if len(content) > 150 else "")
            return {"action": "create_knowledge", "title": title, "content": content}

        return None
    except (json.JSONDecodeError, AiNotConfiguredError, Exception) as e:
        logger.warning("extract_command_with_ai failed: %s", e)
        return None


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


class FinanceTransaction(BaseModel):
    date: str  # YYYY-MM-DD
    amount: float  # + доход, - расход
    type: str  # "income" or "expense"
    category: str
    person_id: Optional[int] = None
    comment: Optional[str] = ""


class FinanceTransactionUpdate(BaseModel):
    """Обновление транзакции (все поля опциональны)."""
    date: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None
    category: Optional[str] = None
    person_id: Optional[int] = None
    comment: Optional[str] = None


class FinanceGoal(BaseModel):
    title: str
    target_amount: float
    current_amount: float = 0
    target_date: Optional[str] = None  # YYYY-MM-DD
    priority: int = 1


class FinanceGoalUpdate(BaseModel):
    """Обновление цели (все поля опциональны)."""
    title: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    target_date: Optional[str] = None
    priority: Optional[int] = None


class FinanceLimit(BaseModel):
    category: str
    amount: float


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
        # Логируем реальные ошибки, кроме "duplicate column name"
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN reminder_enabled INTEGER DEFAULT 0")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" not in msg:
                print(f"[DB MIGRATION] tasks.reminder_enabled failed: {e}")
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN reminder_time TEXT")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" not in msg:
                print(f"[DB MIGRATION] tasks.reminder_time failed: {e}")
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN recurrence_type TEXT DEFAULT 'none'")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" not in msg:
                print(f"[DB MIGRATION] tasks.recurrence_type failed: {e}")
        
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
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS finance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date DATE NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL, -- income / expense
                category TEXT NOT NULL,
                is_fixed INTEGER DEFAULT 0,
                person_id INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS finance_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                target_date DATE,
                priority INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS finance_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category)
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

        # Состояние агента (AgentState v1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_state (
                user_id TEXT PRIMARY KEY,
                persona TEXT,
                active_goals TEXT,
                recent_actions TEXT,
                memory_summary TEXT
            )
        """)
        
        # Миграция: добавляем person_id если нет
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN person_id INTEGER")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" not in msg:
                print(f"[DB MIGRATION] tasks.person_id failed: {e}")
        try:
            await db.execute("ALTER TABLE knowledge ADD COLUMN person_id INTEGER")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" not in msg:
                print(f"[DB MIGRATION] knowledge.person_id failed: {e}")
        
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/api/health")
async def health():
    """
    Простой health-check для nginx/мониторинга.
    Возвращает 200, если:
    - приложение поднято
    - есть доступ к БД
    - (опционально) клиент ИИ инициализирован
    """
    # Проверяем базу
    try:
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute("SELECT 1")
    except Exception as e:
        # Если БД недоступна — сразу 500
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return {
        "status": "ok",
        "db": "ok",
        "ai_client": is_ai_configured(),
    }


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
        data = task.model_dump(exclude_unset=True)
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
    data = person.model_dump(exclude={'fio'})
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
    data = person.model_dump(exclude={'fio'})
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


# === ФИНАНСЫ ===

@app.post("/api/finance/transactions")
async def create_transaction(tx: FinanceTransaction, x_user_id: str = Header(...)):
    if tx.type not in ("income", "expense", "savings"):
        raise HTTPException(status_code=400, detail="type должен быть 'income', 'expense' или 'savings'")
    if not tx.date:
        raise HTTPException(status_code=400, detail="Нужна дата транзакции")
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            """
            INSERT INTO finance_transactions
            (user_id, date, amount, type, category, person_id, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                x_user_id,
                tx.date,
                tx.amount,
                tx.type,
                tx.category,
                tx.person_id,
                tx.comment,
            ),
        )
        await db.commit()
        return {"id": cursor.lastrowid}


@app.get("/api/finance/transactions")
async def list_transactions(
    x_user_id: str = Header(...),
    month: Optional[str] = Query(None, description="YYYY-MM"),
):
    """Список транзакций за месяц (по умолчанию — текущий)."""
    today = datetime.now().date()
    if month:
        try:
            year, m = month.split("-")
            year = int(year)
            m = int(m)
            start = datetime(year, m, 1).date()
        except Exception:
            raise HTTPException(status_code=400, detail="Неверный формат month, нужно YYYY-MM")
    else:
        start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ?
            ORDER BY date DESC, id DESC
            """,
            (x_user_id, start.isoformat(), end.isoformat()),
        )
        return [dict(row) for row in await cursor.fetchall()]


@app.patch("/api/finance/transactions/{tx_id}")
async def update_transaction(tx_id: int, body: FinanceTransactionUpdate, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_transactions WHERE id = ? AND user_id = ?", (tx_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Транзакция не найдена")
        updates = []
        params = []
        if body.date is not None:
            updates.append("date = ?")
            params.append(body.date)
        if body.amount is not None:
            updates.append("amount = ?")
            params.append(body.amount)
        if body.type is not None:
            if body.type not in ("income", "expense", "savings"):
                raise HTTPException(status_code=400, detail="type должен быть 'income', 'expense' или 'savings'")
            updates.append("type = ?")
            params.append(body.type)
        if body.category is not None:
            updates.append("category = ?")
            params.append(body.category)
        if body.person_id is not None:
            updates.append("person_id = ?")
            params.append(body.person_id)
        if body.comment is not None:
            updates.append("comment = ?")
            params.append(body.comment)
        if not updates:
            return {"ok": True}
        params.append(tx_id)
        params.append(x_user_id)
        await db.execute(
            f"UPDATE finance_transactions SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            params,
        )
        await db.commit()
        return {"ok": True}


@app.delete("/api/finance/transactions/{tx_id}")
async def delete_transaction(tx_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_transactions WHERE id = ? AND user_id = ?", (tx_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Транзакция не найдена")
        await db.execute("DELETE FROM finance_transactions WHERE id = ? AND user_id = ?", (tx_id, x_user_id))
        await db.commit()
        return {"ok": True}


@app.post("/api/finance/goals")
async def create_goal(goal: FinanceGoal, x_user_id: str = Header(...)):
    if goal.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount должен быть > 0")
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            """
            INSERT INTO finance_goals
            (user_id, title, target_amount, current_amount, target_date, priority)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                x_user_id,
                goal.title,
                goal.target_amount,
                goal.current_amount,
                goal.target_date,
                goal.priority,
            ),
        )
        await db.commit()
        return {"id": cursor.lastrowid}


@app.get("/api/finance/goals")
async def list_goals(x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM finance_goals WHERE user_id = ? ORDER BY priority ASC, created_at DESC",
            (x_user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


@app.patch("/api/finance/goals/{goal_id}")
async def update_goal(goal_id: int, body: FinanceGoalUpdate, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_goals WHERE id = ? AND user_id = ?", (goal_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Цель не найдена")
        updates = []
        params = []
        if body.title is not None:
            updates.append("title = ?")
            params.append(body.title)
        if body.target_amount is not None:
            if body.target_amount <= 0:
                raise HTTPException(status_code=400, detail="target_amount должен быть > 0")
            updates.append("target_amount = ?")
            params.append(body.target_amount)
        if body.current_amount is not None:
            updates.append("current_amount = ?")
            params.append(body.current_amount)
        if body.target_date is not None:
            updates.append("target_date = ?")
            params.append(body.target_date)
        if body.priority is not None:
            updates.append("priority = ?")
            params.append(body.priority)
        if not updates:
            return {"ok": True}
        params.append(goal_id)
        params.append(x_user_id)
        await db.execute(
            f"UPDATE finance_goals SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            params,
        )
        await db.commit()
        return {"ok": True}


@app.delete("/api/finance/goals/{goal_id}")
async def delete_goal(goal_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_goals WHERE id = ? AND user_id = ?", (goal_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Цель не найдена")
        await db.execute("DELETE FROM finance_goals WHERE id = ? AND user_id = ?", (goal_id, x_user_id))
        await db.commit()
        return {"ok": True}


@app.get("/api/finance/limits")
async def list_limits(x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM finance_limits WHERE user_id = ? ORDER BY category",
            (x_user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


@app.post("/api/finance/limits")
async def create_limit(limit: FinanceLimit, x_user_id: str = Header(...)):
    if limit.amount <= 0:
        raise HTTPException(status_code=400, detail="amount должен быть > 0")
    async with aiosqlite.connect(DATABASE) as db:
        try:
            cursor = await db.execute(
                "INSERT INTO finance_limits (user_id, category, amount) VALUES (?, ?, ?)",
                (x_user_id, limit.category.strip() or "Прочее", limit.amount),
            )
            await db.commit()
            return {"id": cursor.lastrowid}
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=400, detail="Лимит для этой категории уже есть")


@app.patch("/api/finance/limits/{limit_id}")
async def update_limit(limit_id: int, limit: FinanceLimit, x_user_id: str = Header(...)):
    if limit.amount <= 0:
        raise HTTPException(status_code=400, detail="amount должен быть > 0")
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_limits WHERE id = ? AND user_id = ?", (limit_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Лимит не найден")
        await db.execute(
            "UPDATE finance_limits SET category = ?, amount = ? WHERE id = ? AND user_id = ?",
            (limit.category.strip() or "Прочее", limit.amount, limit_id, x_user_id),
        )
        await db.commit()
        return {"ok": True}


@app.delete("/api/finance/limits/{limit_id}")
async def delete_limit(limit_id: int, x_user_id: str = Header(...)):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM finance_limits WHERE id = ? AND user_id = ?", (limit_id, x_user_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Лимит не найден")
        await db.execute("DELETE FROM finance_limits WHERE id = ? AND user_id = ?", (limit_id, x_user_id))
        await db.commit()
        return {"ok": True}


@app.get("/api/finance/summary")
async def finance_summary(
    x_user_id: str = Header(...),
    month: Optional[str] = Query(None, description="YYYY-MM"),
):
    """Сводка по финансам за месяц."""
    today = datetime.now().date()
    if month:
        try:
            year, m = month.split("-")
            year = int(year)
            m = int(m)
            start = datetime(year, m, 1).date()
        except Exception:
            raise HTTPException(status_code=400, detail="Неверный формат month, нужно YYYY-MM")
    else:
        start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        # Остаток предыдущего месяца (перенос)
        if start.month == 1:
            start_prev = start.replace(year=start.year - 1, month=12)
        else:
            start_prev = start.replace(month=start.month - 1)
        end_prev = start
        cursor = await db.execute(
            """
            SELECT
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income_prev,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense_prev
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ?
            """,
            (x_user_id, start_prev.isoformat(), end_prev.isoformat()),
        )
        row_prev = await cursor.fetchone()
        income_prev = row_prev["income_prev"] or 0
        expense_prev = row_prev["expense_prev"] or 0
        previous_balance = income_prev - expense_prev

        # Доходы и расходы за выбранный месяц
        cursor = await db.execute(
            """
            SELECT
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ?
            """,
            (x_user_id, start.isoformat(), end.isoformat()),
        )
        row = await cursor.fetchone()
        income = row["income"] or 0
        expense = row["expense"] or 0
        balance = income - expense

        # Расходы по категориям
        cursor = await db.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ? AND type = 'expense'
            GROUP BY category
            ORDER BY total DESC
            """,
            (x_user_id, start.isoformat(), end.isoformat()),
        )
        expenses_by_category = [dict(row) for row in await cursor.fetchall()]

        # Доходы по категориям
        cursor = await db.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ? AND type = 'income'
            GROUP BY category
            ORDER BY total DESC
            """,
            (x_user_id, start.isoformat(), end.isoformat()),
        )
        incomes_by_category = [dict(row) for row in await cursor.fetchall()]

        # Цели
        cursor = await db.execute(
            "SELECT * FROM finance_goals WHERE user_id = ? ORDER BY priority ASC, created_at DESC",
            (x_user_id,),
        )
        goals_rows = [dict(row) for row in await cursor.fetchall()]

    return {
        "income": income,
        "expense": expense,
        "balance": balance,
        "previous_balance": previous_balance,
        "expenses_by_category": expenses_by_category,
        "incomes_by_category": incomes_by_category,
        "goals": goals_rows,
    }


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

def _extract_birth_date_from_text(text: str):
    """Извлекает дату рождения (DD.MM.YYYY или «дата рождения DD.MM.YYYY») из текста. Возвращает (дата в YYYY-MM-DD или None, текст без даты)."""
    text = text.strip()
    # «дата рождения 04.06.1996» или просто «04.06.1996»
    match = re.search(r'(?:дата\s+рождения\s+)?(\d{1,2}\.\d{1,2}\.\d{4})', text, re.IGNORECASE)
    if not match:
        return None, text
    try:
        d, m, y = match.group(1).split('.')
        date_iso = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        return None, text
    rest = (text[:match.start()] + text[match.end():]).strip()
    rest = re.sub(r'\s+', ' ', rest).strip()
    return date_iso, rest


def _parse_person_roles_strengths_weaknesses(rest: str):
    """Парсит строку после ФИО: роли, сильные и слабые стороны. Возвращает dict с relation, strengths, weaknesses."""
    roles = [
        'мама', 'папа', 'отец', 'мать', 'брат', 'сестра', 'муж', 'жена', 'супруг', 'супруга', 'сын', 'дочь',
        'дядя', 'тётя', 'тетя', 'дед', 'бабушка', 'друг', 'подруга', 'коллега',
        'партнер', 'партнёр', 'партнер по бизнесу', 'партнёр по бизнесу',
        'бизнес партнер', 'бизнес-партнер', 'компаньон', 'сооснователь', 'совладелец',
        'начальник', 'директор', 'менеджер', 'клиент',
        'заказчик', 'поставщик', 'инвестор', 'сосед', 'знакомый'
    ]
    weaknesses_words = [
        'забывчивый', 'забывчива', 'вспыльчивый', 'вспыльчива',
        'ленивый', 'ленива', 'жадный', 'жадная', 'нервный', 'нервная',
        'непунктуальный', 'непунктуальна', 'необязательный', 'необязательна'
    ]
    data = {}
    if not rest:
        return data
    if ',' in rest or ';' in rest:
        parts = [p.strip() for p in re.split(r'[,;]', rest) if p.strip()]
    else:
        parts = rest.split()
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
    return data


def parse_user_command(message: str, user_id: str):
    """Парсит команды пользователя напрямую, без ИИ."""
    # Очищаем от лишнего шума: эмодзи, повторяющихся пробелов
    # Оригинал используем для логирования при необходимости
    msg_lower = message.lower().strip()
    # Убираем простые эмодзи и лишние символы, чтобы не попадали в заголовки задач
    msg_lower = re.sub(r'[^\w\s\.\,\-\:\;\!\?ёа-я0-9]', ' ', msg_lower)
    msg_lower = re.sub(r'\s+', ' ', msg_lower).strip()
    logger.info(f"Parsing message: {msg_lower}")

    # Если это явно вопрос (есть "?") и нет сильных командных слов — ничего не делаем
    if "?" in msg_lower:
        strong_prefixes = (
            "создай задачу", "добавь задачу",
            "создай контакт", "добавь контакт",
            "создай карточку", "добавь карточку", "добавь человека",
        )
        if not msg_lower.startswith(strong_prefixes):
            return None
    
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
    
    soft_patterns = {
        r'нужно\s+(.+)',
        r'надо\s+(.+)',
        r'не забыть\s+(.+)',
    }
    ambiguous_verbs = [
        'подумать', 'поразмышлять', 'обсудить', 'обговорить',
        'поговорить', 'узнать', 'поискать', 'почитать'
    ]

    for pattern in create_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            logger.info(f"Pattern matched: {pattern} -> {match.group(1)}")
            title = match.group(1).strip()
            
            # Защита от нескольких задач в одном сообщении:
            # считаем количество глаголов-действий. Если больше 1 — просим разбить.
            multi_verbs = [
                'купить', 'позвонить', 'написать', 'сделать', 'проверить',
                'отправить', 'подготовить', 'встретиться', 'забрать',
                'оплатить', 'заказать', 'разобраться', 'записаться'
            ]
            verb_count = 0
            for v in multi_verbs:
                if re.search(rf'\b{v}\b', msg_lower):
                    verb_count += 1
            if verb_count > 1:
                logger.info(f"Detected multiple actions in one message (verbs={verb_count}), asking user to split")
                return {
                    "action": "ask_split_tasks"
                }
            
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

            # Если фраза мягкая (нужно/надо/не забыть) и содержит "размытые" глаголы — сначала уточняем
            if pattern in soft_patterns:
                tl = title_clean.lower() or title.lower()
                if any(v in tl for v in ambiguous_verbs):
                    logger.info(f"Ambiguous soft task phrase, asking for confirmation: {tl}")
                    return {
                        "action": "ask_task_confirmation",
                        "title": title_clean.capitalize() if title_clean else title.capitalize(),
                    }
            
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
    
    # --- Сначала финансы и цели, чтобы "добавь цель ..." не матчилось как контакт ---
    # Расход
    expense_patterns = [
        r'(?:добавь\s+)?расход\s+([\d\s]+(?:[.,]\d+)?)\s+(?:на\s+)?(.+)',
        r'потратил[а]?\s+([\d\s]+(?:[.,]\d+)?)\s+(?:на\s+)?(.+)',
        r'трата\s+([\d\s]+(?:[.,]\d+)?)\s+(?:на\s+)?(.+)',
    ]
    for pattern in expense_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            amount_str = m.group(1).replace(',', '.').replace(' ', '').strip()
            rest = m.group(2).strip()
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            if amount <= 0:
                continue
            category = rest
            for suffix in [' сегодня', ' завтра', ' послезавтра']:
                if category.endswith(suffix):
                    category = category[:-len(suffix)].strip()
            date_match = re.search(r'\s+(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$', category)
            if date_match:
                category = re.sub(r'\s+\d{1,2}\.\d{1,2}(?:\.\d{4})?\s*$', '', category).strip()
            if not category or len(category) > 100:
                category = "Прочее"
            tx_date = datetime.now().date().isoformat()
            if 'завтра' in rest:
                tx_date = (datetime.now().date() + timedelta(days=1)).isoformat()
            elif 'послезавтра' in rest:
                tx_date = (datetime.now().date() + timedelta(days=2)).isoformat()
            elif date_match:
                try:
                    day, month = int(date_match.group(1)), int(date_match.group(2))
                    year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
                    tx_date = datetime(year, month, day).date().isoformat()
                except (ValueError, IndexError):
                    pass
            return {"action": "add_finance_transaction", "type": "expense", "amount": amount, "category": category, "date": tx_date}
    
    # Доход
    income_patterns = [
        r'(?:добавь\s+)?доход\s+([\d\s]+(?:[.,]\d+)?)\s*(.*)',
        r'получил[а]?\s+([\d\s]+(?:[.,]\d+)?)\s*(.*)',
    ]
    for pattern in income_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            amount_str = m.group(1).replace(',', '.').replace(' ', '').strip()
            rest = (m.group(2) if m.lastindex >= 2 else "").strip()
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            if amount <= 0:
                continue
            category = rest if rest and len(rest) <= 100 else "Доход"
            tx_date = datetime.now().date().isoformat()
            return {"action": "add_finance_transaction", "type": "income", "amount": amount, "category": category, "date": tx_date}
    
    # Цель (финансовая)
    goal_patterns = [
        r'создай\s+(?:финансовую\s+)?цель\s+(.+?)\s+([\d\s]+(?:[.,]\d+)?)\s*$',
        r'добавь\s+цель\s+(.+?)\s+([\d\s]+(?:[.,]\d+)?)\s*$',
    ]
    for pattern in goal_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            title = m.group(1).strip()
            amount_str = m.group(2).replace(',', '.').replace(' ', '').strip()
            if not title or len(title) > 200:
                continue
            try:
                target = float(amount_str)
            except ValueError:
                continue
            if target <= 0:
                continue
            return {"action": "add_finance_goal", "title": title[:200], "target_amount": target}
    
    # Заметка в базу знаний
    note_patterns = [
        r'добавь\s+заметку\s+(.+)',
        r'добавь\s+в\s+базу\s+(?:знаний\s+)?(.+)',
        r'запиши\s+в\s+базу\s+(?:знаний\s+)?(.+)',
        r'добавь\s+(?:в\s+)?базу\s+знаний\s+(.+)',
    ]
    for pattern in note_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            text = m.group(1).strip()
            if not text or len(text) > 500:
                continue
            title = text[:150] + ("..." if len(text) > 150 else "")
            return {"action": "create_knowledge", "title": title, "content": text}
    
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
        except Exception:
            birth_date = None
        
        data = {}
        if birth_date:
            data['birth_date'] = birth_date
        if rest:
            data.update(_parse_person_roles_strengths_weaknesses(rest))
        logger.info(f"FIO pattern with date: {fio}, birth: {birth_date}, data: {data}")
        
        return {
            "action": "create_person",
            "fio": fio.title(),
            **data
        }
    
    # ФИО без даты (2–4 слова + роль/характеристики)
    # Только если в rest есть запятая (ФИО, роль, черты) или известное слово-роль — иначе "добавь цель отпуск 200000" попадёт сюда
    fio_no_date = r'добавь\s+([а-яё]+\s+[а-яё]+(?:\s+[а-яё]+){0,2})\s+(.+)'
    fio_match2 = re.search(fio_no_date, msg_lower)
    if fio_match2:
        fio = fio_match2.group(1).strip()
        rest = fio_match2.group(2).strip()
        task_words = ['купить', 'позвонить', 'сделать', 'проверить', 'написать', 'отправить', 'забрать', 'оплатить']
        # Не считать контактом: "добавь цель отпуск 200000", "добавь расход 500" и т.д.
        first_word = fio.split()[0].lower() if fio.split() else ''
        if first_word in ('цель', 'расход', 'доход', 'задачу', 'контакт', 'карточку', 'заметку', 'человека'):
            pass
        else:
            role_hint_words = [
                'мама', 'папа', 'сын', 'дочь', 'муж', 'жена', 'супруг', 'супруга', 'коллега', 'друг', 'подруга',
                'начальник', 'клиент', 'партнер', 'компаньон', 'директор', 'брат', 'сестра', 'дед', 'бабушка'
            ]
            rest_lower = rest.lower()
            has_role_hint = ',' in rest or any(r in rest_lower for r in role_hint_words)
            if any(word in fio.lower() for word in task_words):
                pass
            elif not has_role_hint and re.match(r'^[\d\s.,]+$', rest.replace(' ', '')):
                pass
            else:
                birth_date, rest = _extract_birth_date_from_text(rest)
                data = {}
                if birth_date:
                    data['birth_date'] = birth_date
                parsed = _parse_person_roles_strengths_weaknesses(rest)
                data.update(parsed)
                logger.info(f"FIO pattern without date: {fio}, data: {data}")
                return {
                    "action": "create_person",
                    "fio": fio.title(),
                    **data
                }
    
    roles_list = [
        'мама', 'папа', 'отец', 'мать', 'брат', 'сестра', 'муж', 'жена', 'супруг', 'супруга', 'сын', 'дочь',
        'дядя', 'тётя', 'тетя', 'дед', 'бабушка', 'друг', 'подруга', 'коллега',
        'партнер', 'партнёр', 'компаньон', 'сооснователь', 'совладелец',
        'начальник', 'директор', 'менеджер', 'клиент', 'заказчик', 'поставщик', 'инвестор', 'сосед', 'знакомый'
    ]
    for pattern in person_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            text = match.group(1).strip()
            # Сначала извлекаем дату рождения из всего текста
            birth_date, text = _extract_birth_date_from_text(text)
            data = {}
            if birth_date:
                data['birth_date'] = birth_date

            parts = [p.strip() for p in re.split(r'[,;]', text) if p.strip()]
            if not parts:
                continue
            fio_part = parts[0]
            # Последнее слово в первой части может быть ролью (супруга, коллега и т.д.)
            words_fio = fio_part.split()
            if len(words_fio) >= 2 and words_fio[-1].lower() in roles_list:
                fio = ' '.join(words_fio[:-1]).strip()
                data['relation'] = words_fio[-1].title()
            else:
                fio = fio_part
            # Остальные части — характеристики (роли/сильные/слабые)
            rest_parts = parts[1:]
            if rest_parts:
                rest_str = ', '.join(rest_parts)
                parsed = _parse_person_roles_strengths_weaknesses(rest_str)
                if parsed.get('relation') and not data.get('relation'):
                    data['relation'] = parsed['relation']
                elif parsed.get('relation') and data.get('relation'):
                    data['relation'] = data['relation'] + ', ' + parsed['relation']
                if parsed.get('strengths'):
                    data['strengths'] = parsed['strengths']
                if parsed.get('weaknesses'):
                    data['weaknesses'] = parsed['weaknesses']

            logger.info(f"Creating person: {fio}, data: {data}")
            return {
                "action": "create_person",
                "fio": fio.title(),
                **data
            }
    
    # Обновление контакта: "обнови контакт Иванов..., сделай его партнёром по бизнесу"
    update_pattern = r'обнови контакт\s+(.+?)\s*(?:,|–|-)\s*(.+)'
    m_update = re.search(update_pattern, msg_lower)
    if m_update:
        fio_query = m_update.group(1).strip()
        rest = m_update.group(2).strip()
        data = {}
        # Пытаемся распознать роль и характеристики аналогично созданию
        roles = [
            'мама', 'папа', 'отец', 'мать', 'брат', 'сестра', 'муж', 'жена', 'сын', 'дочь',
            'дядя', 'тётя', 'тетя', 'дед', 'бабушка', 'друг', 'подруга', 'коллега',
            'партнер', 'партнёр', 'партнер по бизнесу', 'партнёр по бизнесу',
            'бизнес партнер', 'бизнес-партнер', 'компаньон', 'сооснователь', 'совладелец',
            'начальник', 'директор', 'менеджер', 'клиент',
            'заказчик', 'поставщик', 'инвестор', 'сосед', 'знакомый'
        ]
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
        except Exception:
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
            
            elif action_type == "ask_task_confirmation":
                # Не уверены, что это надо превращать в задачу — спрашиваем явно
                raw_title = action.get("title") or ""
                return (
                    "Я не до конца понимаю, нужно ли добавлять это как задачу:\n"
                    f"«{raw_title}».\n\n"
                    "Если хочешь сохранить это именно как задачу, напиши ещё раз в формате:\n"
                    "«создай задачу …»."
                )
            
            elif action_type == "ask_split_tasks":
                # Явный ответ пользователю: пусть разделит фразу на несколько сообщений
                return (
                    "❗️Я вижу в одном сообщении несколько разных действий.\n"
                    "Пожалуйста, напиши каждую задачу отдельным сообщением, например:\n"
                    "— создай задачу позвонить Елене Кудрявской\n"
                    "— создай задачу купить хлеб и молоко"
                )
            
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
            
            elif action_type == "add_finance_transaction":
                tx_type = action.get("type", "expense")
                amount = action.get("amount")
                category = (action.get("category") or "Прочее").strip()[:200]
                tx_date = action.get("date") or datetime.now().date().isoformat()
                if not amount or amount <= 0:
                    return "❌ Укажи сумму больше нуля"
                if tx_type not in ("income", "expense"):
                    tx_type = "expense"
                await db.execute(
                    """
                    INSERT INTO finance_transactions
                    (user_id, date, amount, type, category, person_id, comment)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (user_id, tx_date, abs(amount), tx_type, category or "Прочее", "")
                )
                await db.commit()
                kind = "Расход" if tx_type == "expense" else "Доход"
                return f"✅ {kind} {amount:.0f} ₽ — {category} ({tx_date})"
            
            elif action_type == "add_finance_goal":
                title = (action.get("title") or "").strip()
                target = action.get("target_amount")
                if not title:
                    return "❌ Укажи название цели"
                if not target or target <= 0:
                    return "❌ Укажи целевую сумму"
                await db.execute(
                    """
                    INSERT INTO finance_goals
                    (user_id, title, target_amount, current_amount, target_date, priority)
                    VALUES (?, ?, ?, 0, NULL, 1)
                    """,
                    (user_id, title[:200], float(target))
                )
                await db.commit()
                return f"✅ Цель создана: {title} — {target:.0f} ₽"
            
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


async def maybe_summarize_chat(user_id: str):
    """
    Если история чата разрослась, сжимает старые сообщения в одно резюме.
    Логика:
    - если записей меньше CHAT_SUMMARY_THRESHOLD — ничего не делаем;
    - берём самые старые CHAT_SUMMARY_CHUNK сообщений и просим ИИ сделать короткое резюме;
    - сохраняем резюме как отдельное сообщение с ролью 'system';
    - исходные старые сообщения удаляем.
    """
    if not is_ai_configured():
        return

    try:
        total = await chat_repo.get_total_count(user_id, db_path=DATABASE)
        if total < CHAT_SUMMARY_THRESHOLD:
            return

        # Берём самые старые сообщения
        rows = await chat_repo.get_oldest_messages(
            user_id,
            CHAT_SUMMARY_CHUNK,
            db_path=DATABASE,
        )
        if not rows:
            return

        # Готовим запрос к ИИ для резюме
        history_messages = [
            {"role": r["role"], "content": r["content"]} for r in rows
        ]
        system_msg = {
            "role": "system",
            "content": (
                "Ты помогаешь сжать историю диалога пользователя с ассистентом.\n"
                "Сделай короткое резюме важных фактов о пользователе, его целях, задачах, людях и контексте.\n"
                "Не пересказывай каждое сообщение, оставь только то, что может пригодиться в будущем.\n"
                "Ответь одним абзацем на русском языке."
            ),
        }

        summary_text = await ai_chat(
            [system_msg] + history_messages,
            model_hint="summary",
            max_tokens=220,
            temperature=0.2,
        )
        if not summary_text:
            return

        # Сохраняем резюме и удаляем старые сообщения
        ids_to_delete = [int(r["id"]) for r in rows]
        await chat_repo.insert_system_message(
            user_id,
            summary_text,
            db_path=DATABASE,
        )
        await chat_repo.delete_messages_by_ids(
            user_id,
            ids_to_delete,
            db_path=DATABASE,
        )
        logger.info(f"Chat history summarized for user {user_id}")
    except Exception as e:
        logger.error(f"Error summarizing chat for user {user_id}: {e}")


@app.post("/api/chat")
async def chat(msg: ChatMessage, x_user_id: str = Header(...)):
    """Чат с ИИ-ассистентом, который знает все данные пользователя."""
    # Единый формат user_id для БД (избегаем расхождений Telegram id как число/строка)
    uid = str(x_user_id).strip() if x_user_id else ""
    if not uid:
        return {"response": "Не указан пользователь (X-User-Id).", "action_executed": False}

    text_raw = msg.message.strip()
    text_lower = text_raw.lower()

    # --- Управление памятью диалога через команды ---
    # Новый диалог / очистка истории
    if text_lower in ("новый диалог", "очистить диалог", "очисти диалог", "reset", "start over"):
        await chat_repo.clear_history(uid, db_path=DATABASE)
        return {
            "response": "Я очистил нашу историю. Можем начать заново с чистого листа.",
            "action_executed": False,
        }

    # Забудь про X — удаляем только те сообщения ассистента, где явно есть фраза
    forget_match = re.match(r"забудь про (.+)", text_lower)
    if forget_match:
        phrase = forget_match.group(1).strip()
        await chat_repo.delete_assistant_messages_with_phrase(
            uid,
            phrase,
            db_path=DATABASE,
        )
        return {
            "response": f"Ок, постараюсь больше не учитывать информацию про «{phrase}».",
            "action_executed": False,
        }

    # Перед обычной обработкой — при необходимости сжимаем очень старую историю в резюме
    await maybe_summarize_chat(uid)

    # Сначала проверяем прямые команды: regex, затем (если пусто) — понимание по сырому тексту через ИИ
    direct_command = parse_user_command(text_raw, uid)
    if not direct_command and is_ai_configured():
        try:
            direct_command = await extract_command_with_ai(text_raw)
            if direct_command:
                logger.info("extract_command_with_ai resolved: %s", direct_command.get("action"))
        except Exception as e:
            logger.warning("extract_command_with_ai error: %s", e)
    if direct_command:
        # Для «добавь контакт» от regex пробуем обогатить поля через ИИ; если команда уже от extract_command_with_ai — не дублируем
        if direct_command.get("action") == "create_person" and is_ai_configured() and not direct_command.get("relation") and not direct_command.get("birth_date"):
            try:
                ai_person = await extract_person_with_ai(text_raw)
                if ai_person and ai_person.get("fio"):
                    direct_command = {"action": "create_person", "fio": ai_person["fio"]}
                    for k in ("relation", "birth_date", "strengths", "weaknesses", "workplace", "benefits", "problems"):
                        if ai_person.get(k):
                            direct_command[k] = ai_person[k]
                    logger.info("create_person: using AI extraction %s", direct_command)
            except Exception as e:
                logger.warning("AI person extraction failed, using regex: %s", e)
        result = await execute_ai_action(direct_command, uid)
        logger.info(f"Direct command executed: {direct_command['action']} -> {result}")
        
        # Решаем, считать ли это реальным действием (меняющим данные)
        action_type = direct_command.get("action")
        is_real_action = action_type not in ("ask_split_tasks", "ask_task_confirmation")
        
        # Сохраняем в историю
        await chat_repo.append_messages(
            uid,
            [
                ("user", msg.message),
                ("assistant", result),
            ],
            db_path=DATABASE,
        )
        
        return {"response": result, "action_executed": is_real_action}
    
    today = datetime.now().date()
    today_iso = today.isoformat()
    # Запрос «что сегодня» — только задачи из БД; «итоги по деньгам» — только финансы из БД (без подмешивания истории)
    is_today_tasks_query = any(
        phrase in text_lower for phrase in (
            "что сегодня", "что у меня сегодня", "какие задачи на сегодня",
            "📋 что сегодня", "задачи на сегодня",
        )
    )
    is_money_summary_query = any(
        phrase in text_lower for phrase in (
            "итоги по деньгам", "💰 итоги по деньгам", "итоги по финансам",
            "сколько потратил", "какой баланс", "доход расход",
        )
    )
    is_goals_query = any(
        phrase in text_lower for phrase in (
            "мои цели", "🎯 мои цели", "какие цели", "финансовые цели", "покажи цели",
        )
    )

    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        
        # Задачи: только не выполненные (done=0), делим на «на сегодня» и «просроченные»
        cursor = await db.execute(
            "SELECT id, title, description, deadline, priority, done FROM tasks WHERE user_id = ? AND done = 0 ORDER BY deadline ASC",
            (uid,)
        )
        active_tasks = [dict(r) for r in await cursor.fetchall()]
        tasks_today = [t for t in active_tasks if t.get("deadline") == today_iso]
        tasks_overdue = [dict(t, **{"_overdue": True}) for t in active_tasks if t.get("deadline") and t["deadline"] < today_iso]
        # Для промпта убираем служебный флаг, оставляем только нужные поля
        _strip = lambda lst: [{"title": x.get("title"), "deadline": x.get("deadline"), "priority": x.get("priority")} for x in lst]
        tasks_today_short = _strip(tasks_today)
        tasks_overdue_short = _strip(tasks_overdue)
        logger.info("Chat context user_id=%s tasks_today=%d tasks_overdue=%d", uid, len(tasks_today), len(tasks_overdue))
        
        if is_today_tasks_query:
            # Ответ только из БД, без ИИ — единый красивый формат
            now = datetime.now()
            today_str = now.strftime("%d.%m.%Y")
            weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
            lines = [f"📅 <b>Сегодня, {weekday}, {today_str}</b>", ""]
            lines.append("📋 <b>На сегодня:</b>")
            if tasks_today_short:
                for t in tasks_today_short:
                    lines.append(f"• {t.get('title', '—')}")
            else:
                lines.append("• Задач нет")
            lines.append("")
            lines.append("⚠️ <b>Просроченные:</b>")
            if tasks_overdue_short:
                for t in tasks_overdue_short:
                    lines.append(f"• {t.get('title', '—')} (дедлайн прошёл)")
            else:
                lines.append("• Нет")
            lines.append("")
            if uid == "anonymous":
                lines.append("💡 Откройте Hub из приложения Telegram (кнопка «Открыть Hub»), чтобы видеть свои задачи.")
            elif not tasks_today_short and not tasks_overdue_short:
                lines.append("💡 Можно добавить задачу в Hub или написать: <i>создай задачу …</i>")
            else:
                lines.append("💡 Управлять задачами: Hub или команда <i>создай задачу …</i>")
            response_today = "\n".join(lines)
            await chat_repo.append_turn_and_trim(uid, msg.message, response_today, CHAT_HISTORY_LIMIT, db_path=DATABASE)
            return {"response": response_today, "action_executed": False}
        
        # Полный контекст: задачи (на сегодня + просроченные), контакты, знания, финансы
        total_tasks = len(active_tasks)
        
        # Люди
        cursor = await db.execute(
            "SELECT fio, data FROM people WHERE user_id = ?",
            (uid,)
        )
        people = []
        for row in await cursor.fetchall():
            p = {"fio": row["fio"]}
            p.update(json.loads(row["data"]))
            people.append(p)
        
        # Знания
        cursor = await db.execute(
            "SELECT title, content, tags FROM knowledge WHERE user_id = ?",
            (uid,)
        )
        knowledge = []
        for row in await cursor.fetchall():
            k = dict(row)
            k["tags"] = json.loads(k["tags"])
            knowledge.append(k)

        # Финансы: сводка за текущий месяц + последние операции и цели
        start_month = today.replace(day=1)
        if start_month.month == 12:
            end_month = start_month.replace(year=start_month.year + 1, month=1)
        else:
            end_month = start_month.replace(month=start_month.month + 1)

        # Доходы и расходы за месяц
        cursor = await db.execute(
            """
            SELECT
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ?
            """,
            (uid, start_month.isoformat(), end_month.isoformat()),
        )
        fin_row = await cursor.fetchone()
        fin_income = (fin_row["income"] or 0) if fin_row else 0
        fin_expense = (fin_row["expense"] or 0) if fin_row else 0
        fin_balance = fin_income - fin_expense

        # Последние операции (ограничим 20)
        cursor = await db.execute(
            """
            SELECT date, amount, type, category, comment
            FROM finance_transactions
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
            LIMIT 20
            """,
            (uid,),
        )
        fin_last_ops = [dict(row) for row in await cursor.fetchall()]

        # Цели
        cursor = await db.execute(
            "SELECT title, target_amount, current_amount, target_date, priority FROM finance_goals WHERE user_id = ? ORDER BY priority ASC, created_at DESC",
            (uid,),
        )
        fin_goals = [dict(row) for row in await cursor.fetchall()]
        
        # Расходы по категориям за текущий месяц (для лимитов)
        cursor = await db.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM finance_transactions
            WHERE user_id = ? AND date >= ? AND date < ? AND type = 'expense'
            GROUP BY category
            """,
            (uid, start_month.isoformat(), end_month.isoformat()),
        )
        expenses_by_category = [dict(row) for row in await cursor.fetchall()]
        
        # Лимиты по категориям
        cursor = await db.execute(
            "SELECT category, amount FROM finance_limits WHERE user_id = ? ORDER BY category",
            (uid,),
        )
        fin_limits = [dict(row) for row in await cursor.fetchall()]
        
        # Запрос «Итоги по деньгам» — ответ только из БД, без ИИ
        if is_money_summary_query:
            now = datetime.now()
            months_ru = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
            month_name = f"{months_ru[now.month - 1]} {now.year}"
            lines = [f"💰 <b>Итоги за {month_name}</b>", ""]
            lines.append(f"• Доход: {fin_income:,.0f} ₽".replace(",", " "))
            lines.append(f"• Расход: {fin_expense:,.0f} ₽".replace(",", " "))
            lines.append(f"• Баланс: {fin_balance:,.0f} ₽".replace(",", " "))
            lines.append("")
            if fin_last_ops:
                lines.append("<b>Последние операции:</b>")
                for op in fin_last_ops[:5]:
                    sign = "+" if op.get("type") == "income" else "−"
                    lines.append(f"  {sign} {op.get('amount', 0):,.0f} ₽ — {op.get('category', '')} ({op.get('date', '')})".replace(",", " "))
            else:
                lines.append("Операций за месяц нет.")
            if uid == "anonymous":
                lines.append("")
                lines.append("💡 Откройте Hub из приложения Telegram, чтобы видеть свои финансы.")
            elif fin_income == 0 and fin_expense == 0 and not fin_last_ops:
                lines.append("")
                lines.append("💡 Если вносили операции в Hub — откройте его по кнопке «Открыть Hub» в этом чате.")
            response_money = "\n".join(lines)
            await chat_repo.append_turn_and_trim(uid, msg.message, response_money, CHAT_HISTORY_LIMIT, db_path=DATABASE)
            return {"response": response_money, "action_executed": False}
        
        # Запрос «Мои цели» — ответ только из БД, без ИИ (никаких Нива/Багги из истории)
        if is_goals_query:
            lines = ["🎯 <b>Финансовые цели</b>", ""]
            if fin_goals:
                for i, g in enumerate(fin_goals, 1):
                    title = g.get("title") or "—"
                    target = g.get("target_amount") or 0
                    current = g.get("current_amount") or 0
                    lines.append(f"{i}. <b>{title}</b> — {target:,.0f} ₽".replace(",", " "))
                    lines.append(f"   Накоплено: {current:,.0f} ₽".replace(",", " "))
                    lines.append("")
            else:
                lines.append("Целей пока нет.")
                lines.append("")
                lines.append("💡 Добавить: Hub → Финансы → Цели или напиши: <i>добавь цель название сумма</i>")
            if uid == "anonymous":
                lines.append("")
                lines.append("💡 Откройте Hub из приложения Telegram, чтобы видеть свои цели.")
            response_goals = "\n".join(lines).strip()
            await chat_repo.append_turn_and_trim(uid, msg.message, response_goals, CHAT_HISTORY_LIMIT, db_path=DATABASE)
            return {"response": response_goals, "action_executed": False}
        
        # Загружаем последние N сообщений для контекста (меньше = быстрее ответ и без устаревших фактов из истории)
        chat_history = await chat_repo.get_recent_history(
            uid,
            CHAT_CONTEXT_MESSAGES,
            db_path=DATABASE,
        )
    
    # Текущая дата и время
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")
    weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
    
    # Сводка по лимитам: потрачено vs лимит по каждой категории
    limits_summary = []
    by_cat = {r["category"]: r["total"] for r in expenses_by_category}
    for lim in fin_limits:
        spent = by_cat.get(lim["category"], 0) or 0
        limit_val = lim["amount"]
        over = spent > limit_val
        limits_summary.append({
            "category": lim["category"],
            "spent": spent,
            "limit": limit_val,
            "over": over,
        })
    
    # Формируем системный промпт
    system_prompt = f"""Ты — ИИ-ассистент YouHub: задачи, контакты, база знаний и финансы в одном месте. Работаешь как агент: даёшь короткие ответы и подсказки по данным пользователя.

⏰ Сейчас: {today_str} ({weekday}), {now.strftime("%H:%M")}

📊 Данные пользователя (используй только их, не выдумывай):
⚠️ Актуальны ТОЛЬКО данные в этом блоке. В истории диалога могли упоминаться старые цели/задачи/операции — пользователь мог их удалить. Не пересказывай цели или факты из истории. Если в блоке написано «Цели: нет» — отвечай, что целей нет; не упоминай цели из прошлых сообщений.
• Задачи из БД: на сегодня (дедлайн сегодня) — {json.dumps(tasks_today_short, ensure_ascii=False) if tasks_today_short else "нет"}; просроченные (дедлайн прошёл) — {json.dumps(tasks_overdue_short, ensure_ascii=False) if tasks_overdue_short else "нет"}. Всего активных (не выполненных): {total_tasks}. Готовые не показывай.
• Контакты ({len(people)}): {json.dumps(people, ensure_ascii=False) if people else "нет"}
• Знания ({len(knowledge)}): {json.dumps(knowledge, ensure_ascii=False) if knowledge else "нет"}
• Финансы (текущий месяц): доход {fin_income}, расход {fin_expense}, баланс {fin_balance}
• Последние операции: {json.dumps(fin_last_ops, ensure_ascii=False) if fin_last_ops else "нет"}
• Цели: {json.dumps(fin_goals, ensure_ascii=False) if fin_goals else "нет"}
• Расход по категориям: {json.dumps(expenses_by_category, ensure_ascii=False) if expenses_by_category else "нет"}
• Лимиты по категориям (потрачено / лимит): {json.dumps(limits_summary, ensure_ascii=False) if limits_summary else "нет"}

🔧 КОМАНДЫ (система выполняет по точной фразе; не путай тип записи):
- Задача: "создай задачу купить молоко на завтра", "выполнено купить молоко"
- Контакт (карточка человека): "добавь контакт Иванов Иван, сын, 01.01.1990" или "добавь контакт ФИО, роль, черты"
- Расход: "добавь расход 500 на еду", "расход 300 транспорт"
- Доход: "добавь доход 3000 зарплата"
- Цель (финансовая): "добавь цель отпуск 200000" или "добавь цель название сумма"
- Заметка: "добавь заметку про встречу с Иваном"
Если пользователь хочет добавить цель — подскажи фразу с словом "цель" и суммой. Если контакт — фразу с "добавь контакт" и ФИО. Не подставляй одно вместо другого.

🎯 Формат ответа:
1) 1–2 предложения по сути.
2) 1–3 конкретных шага или формулировки.
3) Если по лимитам есть превышение (over: true) — кратко предупреди по категории.

🧠 По людям: учитывай strengths/weaknesses, предлагай тактику общения и риски.
📋 По задачам: приоритеты, что отсечь, план на 2–3 шага.
💰 По финансам: бюджет, цели, лимиты. Если лимит по категории превышен — скажи прямо. Не давай советов по акциям/крипте.

📌 Правила:
- Пиши КРАТКО, по-русски. Без воды. Тон — человекоподобный, тёплый, как личный ассистент.
- Опирайся только на данные выше и контекст диалога. Не придумывай факты.
- Не говори "я создал задачу" — действия выполняет система по команде пользователя. Ты лишь подсказываешь команды или анализируешь данные.
- Проактивность: если видишь в задачах встречу/созвон/звонок сегодня или скоро — предложи подготовиться или напомни, что стоит проверить. На вопросы вроде «что у меня сегодня?» — собери из задач и контекста один понятный ответ.
- По финансам и задачам: используй только числа и списки из блока «Данные пользователя». Не повторяй суммы или задачи из истории диалога — они могли устареть."""

    if not is_ai_configured():
        return {"response": "ИИ не настроен. Установите OPENROUTER_API_KEY в .env"}
    
    try:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": msg.message})
        
        ai_response = await ai_chat(
            messages,
            model_hint="chat",
            max_tokens=400,
            temperature=0.4,
        )
        
        # Сохраняем в историю
        await chat_repo.append_turn_and_trim(
            uid,
            msg.message,
            ai_response,
            CHAT_HISTORY_LIMIT,
            db_path=DATABASE,
        )
        
        return {"response": ai_response, "action_executed": False}
    
    except AiNotConfiguredError:
        return {"response": "ИИ не настроен. Установите OPENROUTER_API_KEY в .env"}
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
    await chat_repo.clear_history(x_user_id, db_path=DATABASE)
    return {"status": "ok"}


@app.get("/api/chat/history")
async def get_chat_history(x_user_id: str = Header(...), limit: int = Query(50, ge=1, le=200)):
    """
    Получить последние сообщения диалога для отображения в UI.
    Возвращаем role + content в хронологическом порядке.
    """
    history = await chat_repo.get_recent_history(
        x_user_id,
        limit,
        db_path=DATABASE,
    )
    return {"history": history}


@app.get("/api/agent_state")
async def get_agent_state(x_user_id: str = Header(...)):
    """
    Диагностика: получить текущее состояние агента (AgentState) для пользователя.

    Используется для отладки: посмотреть persona, active_goals, memory_summary, recent_actions.
    """
    uid = str(x_user_id).strip()
    state = await agent_core.load_state(uid)
    return {
        "user_id": state.user_id,
        "persona": state.persona,
        "active_goals": state.active_goals,
        "recent_actions": state.recent_actions,
        "memory_summary": state.memory_summary,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
