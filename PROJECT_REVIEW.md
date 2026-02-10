# Обзор проекта TG Hub (YouHub) — оценка на текущую дату

Краткий отчёт: что работает корректно, что требует внимания, что исправлено.

---

## ✅ Работает корректно

### Точка входа и бот
- **bot.py** — единственная актуальная точка входа: только wiring (Bot, Dispatcher, сервисы, handlers, `scheduler_service.start()`, polling). Без бизнес-логики и SQL.
- **config.py** — BOT_TOKEN, WEBAPP_HUB_URL, API_BASE_URL из .env.
- Регистрация handlers: `/start` до F.text, чтобы команды не уходили в ИИ.

### Storage и репозитории бота
- **storage/database.py** — DatabaseProvider, AiosqliteDatabaseProvider.
- **storage/bootstrap.py** — get_database_provider(), get_tasks_repo(); DATABASE = Path("data/hub.db").
- **tg_hub_bot/repositories/tasks.py** — SqliteTaskRepository(DatabaseProvider), весь SQL по задачам здесь; используется для напоминаний.

### Сервисы (корень)
- **services/ai_service.py** — create_ai_service() → ApiAiService(API_BASE_URL).
- **services/scheduler_service.py** — create_scheduler_service(reminders_service) → SchedulerService.

### Handlers
- **start.py** — /start, reply-клавиатура (Что сегодня?, Итоги по деньгам, Мои цели, Задать вопрос, Открыть Hub), inline-кнопка «Открыть Hub».
- **ai_chat.py** — любой текст → «Думаю…» + ai_service.generate_response(user_id, text) → ответ с ParseMode.HTML.

### API (api/main.py)
- **Инициализация** — init_db() при startup, создание таблиц (tasks, people, knowledge, finance_*, chat_history, timeline и т.д.).
- **Эндпоинты** — задачи, люди, знания, финансы (транзакции, цели, лимиты), timeline, health.
- **Чат /api/chat**:
  - Нормализация user_id (uid = str(x_user_id).strip()).
  - Команды «новый диалог», «забудь про X» обрабатываются отдельно.
  - **Кнопки без ИИ (только БД):**
    - «Что сегодня?» → ответ из БД: задачи на сегодня + просроченные, оформление в коде.
    - «Итоги по деньгам» → доход/расход/баланс/операции из БД, оформление в коде.
    - «Мои цели» → список целей из БД, оформление в коде.
  - Прямые команды: parse_user_command() + при необходимости extract_command_with_ai() → execute_ai_action().
  - Остальные сообщения → полный контекст (задачи, люди, знания, финансы) + история (CHAT_CONTEXT_MESSAGES) → ИИ.
- **История чата** — chat_repo (get_recent_history, append_turn_and_trim, clear_history); сжатие при превышении порога (maybe_summarize_chat).

### ИИ (API)
- **api/services/ai_client.py** — выбор провайдера (OpenRouter / VSELM / Google / Yandex), AsyncOpenAI, chat(messages, model_hint, max_tokens, temperature).
- **Бот** — tg_hub_bot/services/ai.py: ApiAiService, POST на /api/chat с X-User-Id и message; ответ без вызова ИИ для кнопок «Что сегодня?», «Итоги по деньгам», «Мои цели» формируется в API.

### Планировщик и напоминания
- **tg_hub_bot/scheduler.py** — SchedulerService(reminders_service), start(), add_reminder/remove_reminder; регистрация задач 9:00, 12:00, 20:00 и т.д.
- **tg_hub_bot/services/reminders.py** — RemindersService(bot, tasks_repo), отправка напоминаний по задачам.

### Фронтенд
- **hub/** — единое приложение (задачи, люди, знания, финансы); API_URL из config.js; userId из Telegram WebApp initDataUnsafe.user.id; запросы с заголовком X-User-Id.
- **tasks/, people/, knowledge/** — отдельные мини-приложения с собственными config.js (API_URL), при необходимости используются как альтернатива hub.

### Документация
- **ARCHITECTURE.md** — слои бота, API, куда что писать, запреты (ARCH).
- **ARCHITECTURE_AI.md** — поток данных ИИ, понимание по сырому тексту, расширение.
- **DEPLOY.md** — структура на сервере, команды scp и systemctl.

---

## ⚠️ Исправлено в рамках ревью

1. **requirements.txt** — добавлен **aiohttp** (используется в tg_hub_bot/services/ai.py для запросов к API). Без него `pip install -r requirements.txt` и запуск бота приводили бы к ImportError.
2. **tg_hub_bot/app.py** — раньше передавался `SqliteTaskRepository(DATABASE)` (строка), тогда как репозиторий ожидает DatabaseProvider. Заменено на `get_tasks_repo()` из storage.bootstrap, чтобы при запуске через `app.py` (если кто-то им пользуется) не было падения при вызове `self._provider.connection()`.

---

## ⚠️ Требует внимания / ограничения

### README.md
- Устарел: в нём указаны webapp/, webapp-people/ и размещение на GitHub Pages; фактически используются **hub/** (единое приложение), а также tasks/, people/, knowledge/. Имеет смысл обновить README под текущую структуру (hub, API, бот, .env: BOT_TOKEN, WEBAPP_HUB_URL, API_BASE_URL, OPENROUTER_API_KEY и т.д.).

### Альтернативная точка входа app.py
- **tg_hub_bot/app.py** — альтернативная сборка бота (без фабрик services/ai_service и scheduler_service из корня). После правки использует get_tasks_repo(); при этом создаёт ApiAiService и SchedulerService напрямую. Для единообразия и избежания расхождений предпочтительно использовать **bot.py** как единственную точку входа (как в DEPLOY.md).

### API и слой данных
- В **api/main.py** почти все эндпоинты работают с БД через `aiosqlite.connect(DATABASE)` напрямую; репозитории используются только для chat_history. ARCHITECTURE.md допускает это; при росте кода можно вынести задачи/людей/финансы в репозитории API по аналогии с ботом.

### Путь к БД
- Бот (через storage): `data/hub.db` (относительно CWD).
- API: `DATABASE = "data/hub.db"`.
- При запуске из корня проекта (run_all.py, systemd) путь общий — данные общие. Если запускать API/бота из разных каталогов, путь нужно задавать единообразно (например, через переменную окружения).

### Hub и user_id
- Если Hub открыт не из Telegram (нет initData), в запросах уходит `X-User-Id: anonymous`; задачи/финансы тогда сохраняются под "anonymous". В чате бота передаётся Telegram user_id — возможен «разъезд» данных. Подсказки в ответах API («откройте Hub из приложения Telegram») уже есть; при необходимости можно добавить разбор initData на бэкенде для надёжной привязки к Telegram id.

### ИИ (общее)
- Качество ответов и распознавание намерений зависят от модели и промптов. Для кнопок «Что сегодня?», «Итоги по деньгам», «Мои цели» ответы формируются без ИИ по данным БД — поведение предсказуемо. Остальной диалог и extract_command_with_ai зависят от провайдера и настроек (temperature, max_tokens).

---

## Итоговая таблица

| Компонент              | Статус        | Примечание |
|------------------------|---------------|------------|
| bot.py                 | ✅ Корректно  | Единственная рекомендуемая точка входа |
| app.py                 | ✅ Исправлено | Использует get_tasks_repo(); лучше не использовать как основной |
| config.py              | ✅ Корректно  | |
| storage/               | ✅ Корректно  | |
| services/ (корень)     | ✅ Корректно  | |
| tg_hub_bot/handlers    | ✅ Корректно  | |
| tg_hub_bot/repositories| ✅ Корректно  | |
| tg_hub_bot/services    | ✅ Корректно  | aiohttp в requirements добавлен |
| tg_hub_bot/scheduler   | ✅ Корректно  | |
| api/main.py            | ✅ Корректно  | Кнопки — ответы из БД без ИИ; чат и команды — через ИИ/execute_ai_action |
| api/repositories       | ✅ Корректно  | chat_history |
| api/services           | ✅ Корректно  | ai_client |
| hub/                   | ✅ Корректно  | Единое приложение, userId из Telegram |
| requirements.txt       | ✅ Исправлено | Добавлен aiohttp |
| README.md              | ⚠️ Устарел    | Описать hub, API, бот, актуальный .env |

---

Кратко: **основной сценарий (бот + API + hub, кнопки и чат) работает корректно.** Критичные моменты (отсутствующий aiohttp и сломанный app.py) исправлены. Дальнейшие улучшения — обновление README и при желании приведение app.py к тому же wiring, что и bot.py, или отказ от app.py в пользу одного bot.py.
