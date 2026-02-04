"""
TG Hub — Telegram бот с единым Web App + напоминания о задачах.
"""

import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, WEBAPP_HUB_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = "data/hub.db"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура с кнопкой открытия Hub."""
    if WEBAPP_HUB_URL:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚀 Открыть Hub",
                web_app=WebAppInfo(url=WEBAPP_HUB_URL)
            )]
        ])
    return None


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start."""
    # Убираем Reply клавиатуру
    await message.answer("⚡", reply_markup=ReplyKeyboardRemove())
    
    text = (
        "⚡ <b>Hub</b>\n\n"
        "Твой персональный центр управления:\n\n"
        "📋 <b>Задачи</b> — планируй и выполняй\n"
        "👤 <b>Картотека</b> — досье на людей\n"
        "📚 <b>База знаний</b> — храни важное\n"
        "🤖 <b>ИИ-ассистент</b> — скоро\n\n"
        "Нажми кнопку ниже, чтобы начать."
    )
    
    kb = get_main_keyboard()
    
    if not WEBAPP_HUB_URL:
        text += "\n\n<i>⚠️ WEBAPP_HUB_URL не настроен</i>"
    
    await message.answer(text, reply_markup=kb)


async def get_tasks_for_date(date_str: str):
    """Получить задачи на определённую дату."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, title, deadline, priority FROM tasks WHERE deadline = ? AND done = 0",
            (date_str,)
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_overdue_tasks():
    """Получить просроченные задачи."""
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, title, deadline, priority FROM tasks WHERE deadline < ? AND done = 0",
            (today,)
        )
        return [dict(row) for row in await cursor.fetchall()]


async def send_morning_reminder():
    """Утреннее напоминание о задачах на сегодня (9:00)."""
    logger.info("Отправка утренних напоминаний...")
    today = datetime.now().date().isoformat()
    tasks = await get_tasks_for_date(today)
    
    # Группируем по пользователям
    user_tasks = {}
    for task in tasks:
        uid = task['user_id']
        if uid not in user_tasks:
            user_tasks[uid] = []
        user_tasks[uid].append(task)
    
    for user_id, tasks_list in user_tasks.items():
        try:
            priority_icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            text = "☀️ <b>Доброе утро!</b>\n\n"
            text += f"📋 Задачи на сегодня ({len(tasks_list)}):\n\n"
            for t in tasks_list:
                icon = priority_icons.get(t['priority'], '🟡')
                text += f"{icon} {t['title']}\n"
            
            await bot.send_message(int(user_id), text)
            logger.info(f"Напоминание отправлено пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания {user_id}: {e}")


async def send_evening_reminder():
    """Вечернее напоминание о задачах на завтра (20:00)."""
    logger.info("Отправка вечерних напоминаний...")
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    tasks = await get_tasks_for_date(tomorrow)
    
    user_tasks = {}
    for task in tasks:
        uid = task['user_id']
        if uid not in user_tasks:
            user_tasks[uid] = []
        user_tasks[uid].append(task)
    
    for user_id, tasks_list in user_tasks.items():
        try:
            priority_icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            text = "🌙 <b>Планы на завтра</b>\n\n"
            text += f"📋 Задачи ({len(tasks_list)}):\n\n"
            for t in tasks_list:
                icon = priority_icons.get(t['priority'], '🟡')
                text += f"{icon} {t['title']}\n"
            
            await bot.send_message(int(user_id), text)
            logger.info(f"Вечернее напоминание отправлено {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания {user_id}: {e}")


async def send_overdue_reminder():
    """Напоминание о просроченных задачах (12:00)."""
    logger.info("Проверка просроченных задач...")
    tasks = await get_overdue_tasks()
    
    user_tasks = {}
    for task in tasks:
        uid = task['user_id']
        if uid not in user_tasks:
            user_tasks[uid] = []
        user_tasks[uid].append(task)
    
    for user_id, tasks_list in user_tasks.items():
        try:
            text = "⚠️ <b>Просроченные задачи!</b>\n\n"
            for t in tasks_list:
                text += f"⏰ {t['title']} (до {t['deadline']})\n"
            
            await bot.send_message(int(user_id), text)
            logger.info(f"Напоминание о просрочке отправлено {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания {user_id}: {e}")


def setup_scheduler():
    """Настройка расписания напоминаний."""
    # Утром в 9:00 — задачи на сегодня
    scheduler.add_job(send_morning_reminder, CronTrigger(hour=9, minute=0))
    
    # Вечером в 20:00 — задачи на завтра
    scheduler.add_job(send_evening_reminder, CronTrigger(hour=20, minute=0))
    
    # Днём в 12:00 — просроченные задачи
    scheduler.add_job(send_overdue_reminder, CronTrigger(hour=12, minute=0))
    
    logger.info("Scheduler настроен: 9:00 (сегодня), 12:00 (просрочка), 20:00 (завтра)")


async def main():
    logger.info("Запуск бота...")
    
    # Запускаем scheduler
    setup_scheduler()
    scheduler.start()
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
