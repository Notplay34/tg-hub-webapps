"""
TG Hub — Telegram бот с единым Web App + напоминания о задачах.

Точка входа: при наличии пакета tg_hub_bot использует его, иначе — встроенная логика
(чтобы бот работал и без деплоя папки tg_hub_bot).
"""

import asyncio
import logging
from datetime import datetime, timedelta

import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, WEBAPP_HUB_URL, API_BASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = "data/hub.db"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def call_ai(user_id: int, text: str) -> str:
    url = f"{API_BASE_URL.rstrip('/')}/api/chat"
    payload = {"message": text}
    headers = {"Content-Type": "application/json", "X-User-Id": str(user_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {body}")
                data = await resp.json()
    except Exception:
        logger.exception("AI request failed")
        return "❌ Не получилось обратиться к ИИ. Попробуй ещё раз чуть позже."
    answer = data.get("response")
    if not answer:
        return "😕 ИИ не прислал ответа."
    return answer


def get_main_keyboard() -> InlineKeyboardMarkup:
    if not WEBAPP_HUB_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Старт", web_app=WebAppInfo(url=WEBAPP_HUB_URL))]
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer("🧠 YouHub", reply_markup=ReplyKeyboardRemove())
    text = (
        "👋 <b>YouHub</b> — личный хаб: задачи, люди, деньги и ИИ в одном боте.\n\n"
        "Что внутри:\n\n"
        "📋 <b>Задачи</b> — дедлайны, приоритеты, напоминания\n"
        "👤 <b>Люди</b> — досье, связи, заметки\n"
        "📚 <b>База знаний</b> — важное под рукой\n"
        "💰 <b>Финансы</b> — доходы, расходы, цели и лимиты\n"
        "🤖 <b>ИИ-ассистент</b> — можешь просто написать боту вопрос, он ответит по твоим данным.\n\n"
        "Нажми <b>Старт</b> — и за 30 секунд настроишь всё под себя."
    )
    if not WEBAPP_HUB_URL:
        text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
    await message.answer(text, reply_markup=get_main_keyboard())


@dp.message(F.text)
async def chat_with_ai(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return
    await message.answer("🧠 Думаю...", reply_markup=ReplyKeyboardRemove())
    answer = await call_ai(user_id, text)
    await message.answer(answer, parse_mode=ParseMode.HTML)


async def get_tasks_for_date(date_str: str) -> list[dict]:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, title, deadline, priority FROM tasks WHERE deadline = ? AND done = 0",
            (date_str,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_overdue_tasks() -> list[dict]:
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, title, deadline, priority FROM tasks WHERE deadline < ? AND done = 0",
            (today,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def send_reminders_by_time() -> None:
    now = datetime.now()
    today = now.date().isoformat()
    time_str = now.strftime("%H:%M")
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    before_key = f"before_{time_str}"
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT user_id, title, reminder_time, deadline FROM tasks
               WHERE done = 0 AND reminder_enabled = 1
                 AND ((deadline = ? AND reminder_time = ?) OR (deadline = ? AND reminder_time = ?))""",
            (today, time_str, tomorrow, before_key),
        )
        rows = await cursor.fetchall()
    for row in rows:
        try:
            text = (
                f"⏰ <b>Напоминание на сегодня</b>\n\n{row['title']}"
                if row["deadline"] == today
                else f"⏰ <b>Напоминание: завтра срок</b>\n\n{row['title']}"
            )
            await bot.send_message(int(row["user_id"]), text)
        except Exception as e:
            logger.error("Ошибка напоминания %s: %s", row["user_id"], e)


async def send_morning_reminder() -> None:
    today = datetime.now().date().isoformat()
    tasks = await get_tasks_for_date(today)
    user_tasks: dict[str, list] = {}
    for t in tasks:
        user_tasks.setdefault(t["user_id"], []).append(t)
    for uid, lst in user_tasks.items():
        try:
            icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            msg = "☀️ <b>Доброе утро!</b>\n\n📋 Задачи на сегодня (%s):\n\n" % len(lst)
            msg += "\n".join(f"{icons.get(t['priority'], '🟡')} {t['title']}" for t in lst)
            await bot.send_message(int(uid), msg)
        except Exception as e:
            logger.error("Ошибка напоминания %s: %s", uid, e)


async def send_evening_reminder() -> None:
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    tasks = await get_tasks_for_date(tomorrow)
    user_tasks: dict[str, list] = {}
    for t in tasks:
        user_tasks.setdefault(t["user_id"], []).append(t)
    for uid, lst in user_tasks.items():
        try:
            icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            msg = "🌙 <b>Планы на завтра</b>\n\n📋 Задачи (%s):\n\n" % len(lst)
            msg += "\n".join(f"{icons.get(t['priority'], '🟡')} {t['title']}" for t in lst)
            await bot.send_message(int(uid), msg)
        except Exception as e:
            logger.error("Ошибка напоминания %s: %s", uid, e)


async def send_overdue_reminder() -> None:
    tasks = await get_overdue_tasks()
    user_tasks: dict[str, list] = {}
    for t in tasks:
        user_tasks.setdefault(t["user_id"], []).append(t)
    for uid, lst in user_tasks.items():
        try:
            msg = "⚠️ <b>Просроченные задачи!</b>\n\n"
            msg += "\n".join(f"⏰ {t['title']} (до {t['deadline']})" for t in lst)
            await bot.send_message(int(uid), msg)
        except Exception as e:
            logger.error("Ошибка напоминания %s: %s", uid, e)


def setup_scheduler() -> None:
    scheduler.add_job(send_morning_reminder, CronTrigger(hour=9, minute=0))
    scheduler.add_job(send_evening_reminder, CronTrigger(hour=20, minute=0))
    scheduler.add_job(send_overdue_reminder, CronTrigger(hour=12, minute=0))
    scheduler.add_job(send_reminders_by_time, CronTrigger(minute="*"))
    logger.info("Scheduler: 9:00, 12:00, 20:00 + персональное время")


async def main() -> None:
    logger.info("Запуск бота...")
    setup_scheduler()
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
