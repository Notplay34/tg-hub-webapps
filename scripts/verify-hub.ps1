# Проверка: что реально лежит на сервере в hub/
# Запуск: .\scripts\verify-hub.ps1
$server = "root@194.87.103.157"

Write-Host "=== Содержит ли app.js на сервере removeFolderRemnants? ===" -ForegroundColor Cyan
ssh $server "grep -c 'removeFolderRemnants' /opt/tg-hub/hub/app.js 2>/dev/null || echo 0"

Write-Host "`n=== Есть ли watchFolderRemnants? (должно быть 1) ===" -ForegroundColor Cyan
ssh $server "grep -c 'watchFolderRemnants' /opt/tg-hub/hub/app.js 2>/dev/null || echo 0"

Write-Host "`n=== Версия в index.html (v=?) ===" -ForegroundColor Cyan
ssh $server "grep -o 'app.js?v=[0-9]*' /opt/tg-hub/hub/index.html 2>/dev/null || echo 'не найдено'"
