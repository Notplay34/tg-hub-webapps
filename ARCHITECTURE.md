## TG Hub — архитектура

TG Hub состоит из двух основных частей:

- **Telegram‑бот (`tg_hub_bot/`)**
- **HTTP API (`api/`)**

Фронтенд (`hub/`) обращается к API, а бот использует то же API и общую базу данных `data/hub.db`.

Подробно про AI-ассистента (интерфейс, контекст, проактивность): **ARCHITECTURE_AI.md**.

---

## Слои Telegram‑бота (`tg_hub_bot/`)

Бот организован по классической многослойной схеме:

- **Handlers (`tg_hub_bot/handlers/`)**  
  Чистая Telegram‑логика: принимают апдейты, читают команды и текст, вызывают сервисы и формируют ответы пользователю.

- **Services (`tg_hub_bot/services/`)**  
  Бизнес‑логика: работа с напоминаниями, задачами, контактами, интеграция с AI, интерпретация команд пользователя.

- **Repositories (`tg_hub_bot/repositories/`)**
  Доступ к данным только через интерфейсы (TaskRepository и др.). Содержат SQL и маппинг в доменные модели. Получают соединение через **DatabaseProvider** из `storage/`; handlers и services не создают соединений и не знают о типе БД.

- **Storage (`storage/`)**
  - **DatabaseProvider** — единая точка создания соединений с БД (используется при старте приложения).
  - **bootstrap** — фабрики `get_database_provider()`, `get_tasks_repo()`; репозитории получают провайдер и инкапсулируют всю работу с БД.
  - Замена SQLite на PostgreSQL: новая реализация провайдера + репозиториев без изменения handlers и services.

- **Models (`tg_hub_bot/models/`)**  
  Доменные модели (dataclasses/Pydantic): `TaskSummary`, `ReminderTask` и др.  
  Используются сервисами и репозиториями вместо «сырых» dict.

- **Keyboards (`tg_hub_bot/keyboards/`)**  
  Генерация всех inline/Reply‑клавиатур для Telegram.

- **Scheduler (`tg_hub_bot/scheduler.py`)**  
  **SchedulerService** — изолированный сервис планировщика:
  - инициализирует и регистрирует задачи внутри себя (9:00, 12:00, 20:00, каждую минуту);
  - интерфейс: `start()`, `add_reminder(job_id, callback, trigger)`, `remove_reminder(job_id)`;
  - `bot.py` только вызывает `scheduler_service.start()` и не знает про APScheduler;
  - handlers не работают с планировщиком напрямую; при необходимости используют SchedulerService;
  - замена на внешний воркер — новая реализация `SchedulerServiceProtocol` без изменения bot и handlers.

- **App (`tg_hub_bot/app.py`)**  
  Альтернативная точка сборки бота (основной entrypoint — корневой `bot.py`).

**Entrypoint**: корневой `bot.py` — создание Bot/Dispatcher, сервисов, регистрация handlers, `scheduler_service.start()`, polling.

---

## AI‑слой API (`api/`)

Основное приложение FastAPI живёт в файле `api/main.py`.  
Для работы с AI и историей диалога используются отдельные слои:

- **AI‑клиент (`api/services/ai_client.py`)**
  - Инкапсулирует выбор провайдера (`OpenRouter`, `vsellm`, `Google`, `Yandex`) и конфигурацию клиентов.
  - Предоставляет единый интерфейс:
    - `async def chat(messages: list[dict], model_hint: str | None, ...) -> str`
  - Скрывает детали работы с моделями, температурами, токенами и т.п.

- **Репозиторий истории чата (`api/repositories/chat_history.py`)**
  - Отвечает за таблицу `chat_history` в SQLite:
    - чтение и запись сообщений;
    - выборка последних сообщений для контекста;
    - сжатие истории и удаление старых записей;
    - утилиты `append_turn_and_trim`, `get_recent_history`, `clear_history` и др.

- **Маршрут `/api/chat` (`api/main.py`)**
  - Собирает контекст: задачи, контакты, знания, финансы, лимиты.
  - Получает историю диалога из `ChatHistoryRepository`.
  - Формирует системный промпт и список сообщений.
  - Вызывает `AiClient.chat(...)` и возвращает ответ.
  - Сохраняет новый поворот диалога через репозиторий истории.

---

## Планировщик и память чата

- **Планировщик (бот)**
  - **SchedulerService** в `tg_hub_bot/scheduler.py`: инкапсулирует APScheduler, регистрирует напоминания.
  - `bot.py` только вызывает `scheduler_service.start()`; не знает про APScheduler.
  - Может быть вынесен в отдельный процесс/воркер (новая реализация SchedulerServiceProtocol).

- **Память чата (API)**
  - Константы в `api/main.py`:
    - `CHAT_HISTORY_LIMIT` — сколько последних сообщений хранится «как есть»;
    - `CHAT_SUMMARY_CHUNK` — сколько старых сообщений сжимается за раз;
    - `CHAT_SUMMARY_THRESHOLD` — порог, после которого запускается сжатие.
  - Функция `maybe_summarize_chat(user_id)`:
    - если история слишком длинная, запрашивает у AI краткое резюме старых сообщений;
    - сохраняет резюме как системное сообщение;
    - удаляет исходные старые записи через репозиторий истории.

---

## Точки расширения

- **Подмена AI‑провайдера**
  - Реализуется через замену реализации в `api/services/ai_client.py`.
  - Интерфейс `chat(...)` остаётся тем же для `api/main.py`.

- **Замена/расширение БД**
  - Сейчас используется SQLite (`aiosqlite`) и файл `data/hub.db`.
  - **Бот**: SQLite полностью изолирован от `bot.py` и handlers. Соединения создаёт только `storage.database.AiosqliteDatabaseProvider`; репозитории (`TaskRepository`) получают провайдер и содержат весь SQL. Для перехода на PostgreSQL: реализовать `PostgresDatabaseProvider` и, при необходимости, `PostgresTaskRepository`; handlers и services не меняются.
  - **API**: в `api/main.py` по-прежнему есть прямой доступ к БД в эндпоинтах (tasks, people, knowledge, finance и т.д.); для полной изоляции можно ввести такой же слой провайдера и репозиториев.
  - Репозитории позволяют добавлять новые таблицы/сервисы без изменения хэндлеров.

- **Отделение планировщика**
  - SchedulerService создаётся через `create_scheduler_service(reminders_service)` в `bot.py`/`app.py`.
  - Замена на внешний воркер: реализовать другой класс, удовлетворяющий `SchedulerServiceProtocol`, без изменений в bot и handlers.
  - Можно вынести запуск в отдельный процесс (systemd/контейнер), использующий те же RemindersService и репозитории.

- **Расширение доменной модели**
  - Для задач/людей/финансов можно добавлять новые поля:
    - в Pydantic‑модели `Task`, `Person`, `Finance*` в `api/main.py`;
    - в доменные модели и репозитории бота.
  - API и бот продолжают общаться через стабильные модели и сервисы.

---

## Структура для разработчиков: куда что писать

| Нужно сделать | Куда писать | Не писать |
|---------------|-------------|-----------|
| Новая команда/кнопка, ответ на апдейт | `tg_hub_bot/handlers/` | Бизнес-логику, SQL |
| Правила напоминаний, вызов ИИ, доменная логика | `tg_hub_bot/services/` | SQL, прямую работу с БД |
| Запросы к БД, новые таблицы/поля | `tg_hub_bot/repositories/` или `storage/` | SQL в handlers/services/bot.py |
| Создание соединения с БД, фабрики репозиториев | `storage/bootstrap.py`, `storage/database.py` | Логику приложения |
| Точка входа, сборка Bot/Dispatcher, регистрация handlers | `bot.py` | Всё остальное (логику — в services) |

**Запреты (см. комментарии ARCH в коде):** бизнес-логика в handlers; SQL вне repositories; любая логика в bot.py.

