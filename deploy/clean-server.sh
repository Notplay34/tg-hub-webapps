#!/bin/bash
# Удалить всё старое с сервера перед деплоем в Docker

set -e

echo "=== TG Hub — очистка сервера ==="

# Остановить systemd-сервисы (если были)
if systemctl list-units --type=service | grep -q tg-hub; then
    echo "Останавливаю systemd-сервисы..."
    sudo systemctl stop tg-hub-api 2>/dev/null || true
    sudo systemctl stop tg-hub-bot 2>/dev/null || true
    sudo systemctl disable tg-hub-api 2>/dev/null || true
    sudo systemctl disable tg-hub-bot 2>/dev/null || true
fi

# Остановить и удалить Docker-контейнеры/образы tg_hub (если были)
if command -v docker &>/dev/null; then
    echo "Останавливаю Docker-контейнеры tg_hub..."
    cd /opt/tg_hub 2>/dev/null && docker compose down -v 2>/dev/null || true
    docker stop tg_hub-api tg_hub-bot 2>/dev/null || true
    docker rm tg_hub-api tg_hub-bot 2>/dev/null || true
fi

# Удалить старую директорию (оставляем опционально — можно сохранить .env и data)
echo "Удаляю /opt/tg_hub..."
sudo rm -rf /opt/tg_hub

# Создать чистую директорию
sudo mkdir -p /opt/tg_hub
sudo chown $(whoami):$(whoami) /opt/tg_hub

echo ""
echo "Готово. Сервер очищен. Можно деплоить."
