#!/usr/bin/env python3
"""
Удаляет БД и создаёт новую с тестовыми данными.

Использование:
  python scripts/seed_test_data.py
  python scripts/seed_test_data.py --user-id 123456789   # твой Telegram ID (узнать: @userinfobot)
  python scripts/seed_test_data.py --no-wipe --user-id X  # только добавить данные, не удалять БД

Данные выглядят как будто их заполнил живой человек: задачи, проекты,
контакты, финансы, цели.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite

DATABASE = "data/hub.db"

# Тестовый user_id — подставь свой Telegram ID, чтобы видеть данные в Hub
DEFAULT_USER_ID = "0"  # 0 = аноним/тест; для своего Hub укажи --user-id


async def wipe_and_recreate():
    """Удаляем БД и вызываем init_db."""
    db_path = Path(DATABASE)
    if db_path.exists():
        db_path.unlink()
        print(f"Удалена БД: {db_path}")
    
    # Импортируем init_db из API
    try:
        from api.main import init_db
    except ImportError:
        from main import init_db
    await init_db()
    print("БД создана заново")


async def seed(user_id: str):
    """Заполняет БД тестовыми данными."""
    from datetime import date as date_type
    
    today = date.today()
    
    async with aiosqlite.connect(DATABASE) as db:
        # === ЛЮДИ ===
        people_data = [
            ("Иван Петров", {"relation": "коллега", "workplace": "ООО Рога и копыта", "birth_date": "1985-03-12", "groups": ["работа"]}),
            ("Мария Сидорова", {"relation": "жена", "birth_date": "1990-07-22", "groups": ["семья"], "strengths": "отлично организует"}),
            ("Алексей Козлов", {"relation": "подрядчик", "workplace": "РемонтПодряд", "groups": ["ремонт"]}),
            ("Ольга Новикова", {"relation": "друг", "groups": ["друзья"]}),
        ]
        for fio, data in people_data:
            await db.execute(
                "INSERT INTO people (user_id, fio, data) VALUES (?, ?, ?)",
                (user_id, fio, json.dumps(data, ensure_ascii=False))
            )
        
        people_ids = [r for r in range(1, len(people_data) + 1)]
        
        # === ПРОЕКТЫ ===
        projects = [
            ("Ремонт квартиры", "Косметический ремонт в гостиной", 150000, 0, (today + timedelta(days=60)).isoformat()),
            ("Отпуск на море", "Июль, Сочи", 80000, 25000, (today + timedelta(days=90)).isoformat()),
        ]
        for title, desc, budget, rev_goal, deadline in projects:
            await db.execute(
                """INSERT INTO projects (user_id, title, description, status, budget, revenue_goal, deadline)
                   VALUES (?, ?, ?, 'active', ?, ?, ?)""",
                (user_id, title, desc, budget, rev_goal, deadline)
            )
        
        # === ЗАДАЧИ (часть привязана к проектам) ===
        task_project_map = [
            (1, 1), (2, 1), (3, 1), (4, None), (5, None), (6, 2), (7, None), (8, 1), (9, None), (10, None),
        ]
        tasks = [
            ("Выбрать обои для гостиной", None, today.isoformat(), "medium", 0, 1),
            ("Договориться с электриком", "Позвонить Алексею", (today + timedelta(days=3)).isoformat(), "high", 0, 1),
            ("Купить шпаклёвку", None, (today + timedelta(days=5)).isoformat(), "medium", 1, 1),
            ("Позвонить маме", None, today.isoformat(), "low", 0, None),
            ("Забрать посылку на почте", None, (today + timedelta(days=1)).isoformat(), "medium", 0, None),
            ("Купить билеты на самолёт", "Москва — Сочи", (today + timedelta(days=14)).isoformat(), "high", 0, 2),
            ("Сдать отчёт по проекту", None, (today - timedelta(days=2)).isoformat(), "high", 0, None),
            ("Заказать доставку плитки", None, (today + timedelta(days=7)).isoformat(), "medium", 0, 1),
            ("Записаться к стоматологу", None, None, "low", 0, None),
            ("Обновить резюме на hh.ru", None, (today + timedelta(days=10)).isoformat(), "medium", 0, None),
        ]
        for i, (title, desc, deadline, priority, done, project_id) in enumerate(tasks):
            person_id = people_ids[i % len(people_ids)] if i < 4 else None
            await db.execute(
                """INSERT INTO tasks (user_id, title, description, deadline, priority, done, person_id, project_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, title, desc, deadline, priority, done, person_id, project_id)
            )
        
        # === ФИНАНСЫ: транзакции за последние 30 дней ===
        categories_expense = ["еда", "транспорт", "продукты", "развлечения", "коммуналка", "здоровье", "ремонт"]
        categories_income = ["зарплата", "фриланс"]
        
        for d in range(30):
            dt = today - timedelta(days=d)
            # Доход раз в 2 недели
            if d % 14 == 0:
                await db.execute(
                    """INSERT INTO finance_transactions (user_id, date, amount, type, category, comment)
                       VALUES (?, ?, ?, 'income', ?, ?)""",
                    (user_id, dt.isoformat(), 75000 if d == 0 else 72000, "зарплата", "основная")
                )
            # Расходы почти каждый день
            if d < 15:
                amt = [320, 150, 450, 1200, 89][d % 5]
                cat = categories_expense[d % len(categories_expense)]
                await db.execute(
                    """INSERT INTO finance_transactions (user_id, date, amount, type, category, comment)
                       VALUES (?, ?, ?, 'expense', ?, ?)""",
                    (user_id, dt.isoformat(), amt, cat, "обед" if cat == "еда" else None)
                )
            if d == 3:
                await db.execute(
                    """INSERT INTO finance_transactions (user_id, date, amount, type, category, comment)
                       VALUES (?, ?, ?, 'expense', 'ремонт', 'обои')""",
                    (user_id, dt.isoformat(), 8500)
                )
        
        # === ФИНАНСОВЫЕ ЦЕЛИ ===
        goals = [
            ("Отпуск", 150000, 45000, (today + timedelta(days=120)).isoformat()),
            ("Новый ноутбук", 85000, 22000, None),
            ("Подушка на чёрный день", 200000, 78000, None),
        ]
        for title, target, current, target_date in goals:
            await db.execute(
                """INSERT INTO finance_goals (user_id, title, target_amount, current_amount, target_date, priority)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, title, target, current, target_date, 1)
            )
        
        # === ЛИМИТЫ ПО КАТЕГОРИЯМ ===
        for cat, lim in [("еда", 15000), ("транспорт", 8000), ("развлечения", 5000)]:
            await db.execute(
                "INSERT OR REPLACE INTO finance_limits (user_id, category, amount) VALUES (?, ?, ?)",
                (user_id, cat, lim)
            )
        
        # === ЗАМЕТКИ К ПРОЕКТАМ ===
        await db.execute(
            "INSERT INTO project_notes (project_id, text) VALUES (1, 'Договорились с Алексеем на субботу. Материалы закупаем сами.')"
        )
        await db.execute(
            "INSERT INTO project_notes (project_id, text) VALUES (2, 'Отель забронирован 15–22 июля. Осталось билеты.')"
        )
        
        # === УЧАСТНИКИ ПРОЕКТОВ ===
        await db.execute(
            "INSERT INTO project_members (project_id, person_id, role) VALUES (1, 3, 'электрик')"
        )
        await db.execute(
            "INSERT INTO project_members (project_id, person_id, role) VALUES (1, 1, 'помощник')"
        )
        
        await db.commit()
    
    print(f"Заполнено для user_id={user_id}: люди, проекты, задачи, финансы, цели, лимиты")


async def main():
    parser = argparse.ArgumentParser(description="Удалить БД и создать тестовые данные")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="Telegram user_id (подставь свой чтобы видеть в Hub)")
    parser.add_argument("--no-wipe", action="store_true", help="Не удалять БД, только добавить данные")
    args = parser.parse_args()
    
    if not args.no_wipe:
        await wipe_and_recreate()
    else:
        # Очищаем только данные этого юзера
        async with aiosqlite.connect(DATABASE) as db:
            for table in ["tasks", "people", "projects", "finance_transactions", "finance_goals", "finance_limits"]:
                try:
                    await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (args.user_id,))
                except Exception:
                    pass
            await db.commit()
        print(f"Очищены данные user_id={args.user_id}")
    
    await seed(args.user_id)
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
