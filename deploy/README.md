# Деплой на VPS

## Требования

- Ubuntu 22.04+
- Python 3.10+
- Домен (или IP)
- SSL сертификат (Let's Encrypt)

## 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и Nginx
sudo apt install python3 python3-pip python3-venv nginx certbot python3-certbot-nginx -y
```

## 2. Загрузка проекта

```bash
# Создаём папку
mkdir -p /opt/tg-hub
cd /opt/tg-hub

# Клонируем репозиторий (или загружаем файлы)
git clone https://github.com/Notplay34/tg-hub-webapps.git .

# Или загружаем через scp с локальной машины:
# scp -r c:\dev\tg_hub\* user@your-vps:/opt/tg-hub/
```

## 3. Настройка Python

```bash
cd /opt/tg-hub

# Создаём виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt
```

## 4. Настройка .env

```bash
cp .env.example .env
nano .env
```

```env
BOT_TOKEN=ваш_токен
WEBAPP_TASKS_URL=https://ваш-домен.com/tasks/
WEBAPP_PEOPLE_URL=https://ваш-домен.com/people/
```

## 5. Настройка Nginx

```bash
sudo nano /etc/nginx/sites-available/tg-hub
```

```nginx
server {
    listen 80;
    server_name ваш-домен.com;

    # Статика Web Apps
    location /tasks/ {
        alias /opt/tg-hub/tasks/;
        index index.html;
    }
    
    location /people/ {
        alias /opt/tg-hub/people/;
        index index.html;
    }

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Активируем сайт
sudo ln -s /etc/nginx/sites-available/tg-hub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 6. SSL сертификат (HTTPS)

```bash
sudo certbot --nginx -d ваш-домен.com
```

## 7. Systemd сервисы

### Бот

```bash
sudo nano /etc/systemd/system/tg-hub-bot.service
```

```ini
[Unit]
Description=TG Hub Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tg-hub
Environment=PATH=/opt/tg-hub/venv/bin
ExecStart=/opt/tg-hub/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### API

```bash
sudo nano /etc/systemd/system/tg-hub-api.service
```

```ini
[Unit]
Description=TG Hub API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tg-hub
Environment=PATH=/opt/tg-hub/venv/bin
ExecStart=/opt/tg-hub/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Запуск сервисов

```bash
sudo systemctl daemon-reload
sudo systemctl enable tg-hub-bot tg-hub-api
sudo systemctl start tg-hub-bot tg-hub-api
```

## 8. Проверка

```bash
# Статус сервисов
sudo systemctl status tg-hub-bot
sudo systemctl status tg-hub-api

# Логи
sudo journalctl -u tg-hub-bot -f
sudo journalctl -u tg-hub-api -f
```

## 9. Обновление config.js

После деплоя обновите `config.js` в папках `tasks/` и `people/`:

```javascript
window.API_URL = 'https://ваш-домен.com';
```

## Готово!

Теперь:
- Бот работает 24/7
- Web Apps доступны по HTTPS
- Данные хранятся на сервере
- Синхронизация между устройствами
