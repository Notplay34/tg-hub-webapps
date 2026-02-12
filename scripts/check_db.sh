#!/bin/bash
# Проверка БД на сервере (sqlite3 может не быть — используем Python)
cd /opt/tg-hub 2>/dev/null || true
python3 -c "
import sqlite3
conn = sqlite3.connect('data/hub.db')
c = conn.cursor()
print('=== user_id, кол-во задач ===')
for row in c.execute('SELECT user_id, COUNT(*) FROM tasks GROUP BY user_id'):
    print(row)
print()
print('=== Последние 5 задач ===')
for row in c.execute('SELECT id, user_id, title, deadline, done FROM tasks ORDER BY id DESC LIMIT 5'):
    print(row)
conn.close()
"
