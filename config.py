"""Конфигурация бота."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env")

# Единое приложение Hub
WEBAPP_HUB_URL = os.getenv("WEBAPP_HUB_URL", "")

# Базовый URL API (для бота, чтобы ходить в /api/chat)
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Оплата Stars (эквивалент ~100 ₽). 0 = отключить, доступ всем
PAYMENT_STARS = int(os.getenv("PAYMENT_STARS", "100"))
