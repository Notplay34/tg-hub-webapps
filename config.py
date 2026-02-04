"""Конфигурация бота."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env")

# Единое приложение Hub
WEBAPP_HUB_URL = os.getenv("WEBAPP_HUB_URL", "")
