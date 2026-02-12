# Деплой TG Hub в Docker

## 1. Очистка сервера (если был старый деплой)

**На сервере:**
```bash
# Или скопируй и выполни deploy/clean-server.sh
sudo systemctl stop tg-hub-api tg-hub-bot 2>/dev/null || true
sudo rm -rf /opt/tg_hub
sudo mkdir -p /opt/tg_hub
sudo chown $USER:$USER /opt/tg_hub
```

## 2. Установка Docker (если нет)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# выйти и зайти по ssh снова
```

## 3. Копирование проекта на сервер

**С ПК (PowerShell):**
```powershell
cd c:\dev\tg_hub
scp -r * root@194.87.103.157:/opt/tg_hub/
# или через rsync: rsync -avz --exclude .git --exclude __pycache__ . root@194.87.103.157:/opt/tg_hub/
```

**Не забудь .env** — скопируй отдельно (он в .gitignore):
```powershell
scp .env root@194.87.103.157:/opt/tg_hub/
```

## 4. .env на сервере

В `/opt/tg_hub/.env` должны быть:
```
BOT_TOKEN=...
WEBAPP_HUB_URL=https://твой-домен.duckdns.org/hub/
OPENROUTER_API_KEY=...
AI_MODEL=auto
```

## 5. Запуск

**На сервере:**
```bash
cd /opt/tg_hub
docker compose up -d --build
```

Проверка:
```bash
docker compose ps
docker compose logs -f
```

API: `http://сервер:8000`  
Бот подключается к API по внутренней сети (`http://api:8000`).

## 6. Nginx (на хосте) — для HTTPS и Hub

Установи nginx и certbot:
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

Создай конфиг `/etc/nginx/sites-available/tghub`:
```nginx
server {
    listen 80;
    server_name tghub.duckdns.org;
    location / {
        return 301 https://$host$request_uri;
    }
}
server {
    listen 443 ssl;
    server_name tghub.duckdns.org;
    ssl_certificate /etc/letsencrypt/live/tghub.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tghub.duckdns.org/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /hub/ {
        alias /opt/tg_hub/hub/;
        index index.html;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}
```

Получение SSL:
```bash
sudo certbot --nginx -d tghub.duckdns.org
```

Правка hub/config.js — `API_URL` должен быть `https://tghub.duckdns.org` (без /api).

## 7. Перезапуск после изменений

```bash
cd /opt/tg_hub
docker compose up -d --build
```

---

**БД:** хранится в volume `tg_hub_data`. При `docker compose down -v` объём удалится — данные потеряются.
