# Деплой изменений

Команды для выката изменений после правок в коде. Выполнять **сначала на ПК**, затем **на сервере**.

---

## На ПК (PowerShell)

Копирование файлов на сервер (подставьте свой IP или хост вместо `194.87.103.157`):

```powershell
cd c:\dev\tg_hub

# API и бот
scp api\main.py root@194.87.103.157:/opt/tg-hub/api/
scp bot.py root@194.87.103.157:/opt/tg-hub/

# Хаб (фронт)
scp hub\index.html hub\app.js hub\style.css root@194.87.103.157:/opt/tg-hub/hub/
```

---

## На сервере (SSH)

Подключение и перезапуск сервисов:

```bash
ssh root@194.87.103.157
```

После входа на сервер:

```bash
systemctl restart tg-hub-api
systemctl restart tg-hub-bot
```

Проверка статуса:

```bash
systemctl status tg-hub-api tg-hub-bot
```

---

## Кратко

| Где   | Действие |
|-------|----------|
| **ПК** | `scp` — копировать изменённые файлы на сервер |
| **Сервер** | `systemctl restart tg-hub-api` и `tg-hub-bot` — перезапустить сервисы |
