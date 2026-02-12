# Проверка БД на сервере: .\scripts\check_db.ps1
ssh root@194.87.103.157 "cd /opt/tg-hub; echo '=== user_id, tasks ==='; sqlite3 data/hub.db 'SELECT user_id, COUNT(*) FROM tasks GROUP BY user_id;'; echo ''; sqlite3 -header data/hub.db 'SELECT id, user_id, title, deadline FROM tasks ORDER BY id DESC LIMIT 5;'"
