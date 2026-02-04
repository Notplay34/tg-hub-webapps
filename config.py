"""Конфигурация бота."""

import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env")

# URL Web Apps (должны быть HTTPS)
WEBAPP_TASKS_URL = os.getenv("WEBAPP_TASKS_URL", "")
WEBAPP_PEOPLE_URL = os.getenv("WEBAPP_PEOPLE_URL", "")
WEBAPP_KNOWLEDGE_URL = os.getenv("WEBAPP_KNOWLEDGE_URL", "")
