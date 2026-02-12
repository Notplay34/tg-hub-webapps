#!/bin/bash
# SSL через sslip.io — домен резолвится по IP, certbot проходит без проблем с Duck DNS

set -e

echo "=== TG Hub — настройка SSL (sslip.io) ==="

# Получаем внешний IP
IP=$(curl -4 -s ifconfig.me 2>/dev/null || curl -4 -s icanhazip.com)
if [ -z "$IP" ]; then
    echo "Не удалось получить IP"
    exit 1
fi

DOMAIN="${IP}.sslip.io"
echo "Домен: $DOMAIN (IP: $IP)"

# Nginx конфиг
cat > /etc/nginx/sites-available/tghub << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /hub/ {
        alias /opt/tg_hub/hub/;
        index index.html;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}
EOF

# Включаем сайт, отключаем default
ln -sf /etc/nginx/sites-available/tghub /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Certbot
echo "Получение SSL..."
certbot --nginx -d "$DOMAIN" --email sergeyk-09@mail.ru --agree-tos --non-interactive

# Обновляем .env
HUB_URL="https://${DOMAIN}/hub/"
if [ -f /opt/tg_hub/.env ]; then
    if grep -q "WEBAPP_HUB_URL=" /opt/tg_hub/.env; then
        sed -i "s|WEBAPP_HUB_URL=.*|WEBAPP_HUB_URL=$HUB_URL|" /opt/tg_hub/.env
    else
        echo "WEBAPP_HUB_URL=$HUB_URL" >> /opt/tg_hub/.env
    fi
fi

echo ""
echo "=== Готово ==="
echo "Hub URL: $HUB_URL"
echo ""
echo "Обнови .env на ПК: WEBAPP_HUB_URL=$HUB_URL"
echo "В BotFather (если нужен Menu Button): $HUB_URL"
echo ""
echo "Перезапусти бота: cd /opt/tg_hub && docker compose restart bot"
echo "Проверь: https://$DOMAIN/hub/"
