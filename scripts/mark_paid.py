#!/usr/bin/env python3
"""
Добавить пользователя в paid_users (вручную, без оплаты).

Использование:
  python scripts/mark_paid.py --user-id 827628064
  docker compose run --rm api python scripts/mark_paid.py --user-id 827628064
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATABASE = "data/hub.db"


def mark_paid(user_id: str) -> None:
    Path("data").mkdir(exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS paid_users (
                user_id TEXT PRIMARY KEY,
                telegram_payment_charge_id TEXT,
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute(
            """INSERT OR REPLACE INTO paid_users (user_id, telegram_payment_charge_id, paid_at)
               VALUES (?, 'manual', CURRENT_TIMESTAMP)""",
            (str(user_id),),
        )
        db.commit()
    print(f"✓ user_id {user_id} отмечен как оплативший")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True, help="Telegram user_id")
    args = ap.parse_args()
    mark_paid(args.user_id)
