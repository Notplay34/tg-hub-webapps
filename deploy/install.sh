#!/bin/bash
# Скрипт быстрой установки на Ubuntu VPS

set -e

echo "=== TG Hub — установка ==="

# Обновление системы
echo "Обновление системы..."
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
echo "Установка Python, Nginx..."
sudo apt install python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git -y

# Создание директории
echo "Создание директории..."
sudo mkdir -p /opt/tg-hub
cd /opt/tg-hub

# Виртуальное окружение
echo "Настройка Python..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Следующие шаги:"
echo "1. Загрузите файлы проекта в /opt/tg-hub"
echo "2. pip install -r requirements.txt"
echo "3. Настройте .env"
echo "4. Настройте Nginx (см. README.md)"
echo "5. Настройте systemd сервисы"
echo "6. Получите SSL сертификат"
