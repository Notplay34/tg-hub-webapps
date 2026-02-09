# Деплой TG Hub

## Структура на сервере

Файлы лежат в `/opt/tg-hub/`:

- `bot.py` — точка входа бота
- `tg_hub_bot/` — пакет бота (handlers, services, repositories, models, scheduler)
- `api/` — FastAPI
- `hub/` — фронт хаба
- `config.py`, `requirements.txt`, `.env` и т.д.

## Первый деплой пакета бота (tg_hub_bot)

Если на сервере ещё нет каталога `tg_hub_bot` со всеми подпапками, один раз загрузите весь пакет:

**PowerShell (на ПК):**
```powershell
cd c:\dev\tg_hub
scp -r tg_hub_bot root@194.87.103.157:/opt/tg-hub/
```

После этого можно копировать отдельные файлы в `tg_hub_bot/repositories/`, `tg_hub_bot/services/`, `tg_hub_bot/models/` и т.д.

## Обычный деплой после изменений

Копировать только изменённые файлы.

**На ПК (PowerShell):**
```powershell
cd c:\dev\tg_hub
# API
scp api\main.py root@194.87.103.157:/opt/tg-hub/api/

# Бот (точка входа)
scp bot.py root@194.87.103.157:/opt/tg-hub/

# Пакет бота — только изменённые файлы, например:
scp tg_hub_bot\app.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/
scp tg_hub_bot\repositories\tasks.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/repositories/
scp tg_hub_bot\services\reminders.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/services/
scp tg_hub_bot\models\__init__.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/models/
# и т.д.

# Фронт хаба
scp hub\index.html hub\app.js hub\style.css root@194.87.103.157:/opt/tg-hub/hub/
```

**На сервере (после ssh):**
```bash
systemctl restart tg-hub-api
systemctl restart tg-hub-bot
```

---

## Деплой после последних изменений

Что меняли: bootstrap bot.py, вынос AI/scheduler/storage, изоляция БД (DatabaseProvider, TaskRepository).

**На ПК (PowerShell):**
```powershell
cd c:\dev\tg_hub
scp bot.py root@194.87.103.157:/opt/tg-hub/
scp -r storage root@194.87.103.157:/opt/tg-hub/
scp -r services root@194.87.103.157:/opt/tg-hub/
scp tg_hub_bot\handlers\start.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/handlers/
scp tg_hub_bot\repositories\tasks.py root@194.87.103.157:/opt/tg-hub/tg_hub_bot/repositories/
```

**На сервере:**
```bash
systemctl restart tg-hub-bot
```
