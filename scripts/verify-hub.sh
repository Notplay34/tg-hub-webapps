#!/bin/bash
# Проверка hub на сервере. Запуск: bash scripts/verify-hub.sh
# (или на сервере: bash /opt/tg-hub/scripts/verify-hub.sh)

HUB_DIR="${1:-/opt/tg-hub/hub}"

echo "=== removeFolderRemnants в app.js? ==="
grep -c 'removeFolderRemnants' "$HUB_DIR/app.js" 2>/dev/null || echo 0

echo ""
echo "=== watchFolderRemnants в app.js? (должно быть 1+) ==="
grep -c 'watchFolderRemnants' "$HUB_DIR/app.js" 2>/dev/null || echo 0

echo ""
echo "=== Версия app.js в index.html ==="
grep -o 'app.js?v=[0-9]*' "$HUB_DIR/index.html" 2>/dev/null || echo "не найдено"
