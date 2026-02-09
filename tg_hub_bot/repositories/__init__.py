"""
Пакет репозиториев бота.

ARCH: Весь SQL и работа с БД (aiosqlite, execute, курсоры) — ТОЛЬКО здесь.
Handlers и services не содержат SQL; получают данные через интерфейсы
(TaskRepository и др.). Соединение — через storage.DatabaseProvider.
"""

