# Как добавить no-cache для Hub в nginx

## 1. Подключись к серверу
```bash
ssh root@194.87.103.157
```

## 2. Найди конфиг nginx
```bash
# Обычно тут:
ls -la /etc/nginx/sites-enabled/

# Или:
ls -la /etc/nginx/conf.d/
```

Открой файл, где есть `location /hub/`:
```bash
grep -r "location /hub" /etc/nginx/
```

## 3. Редактируй конфиг
```bash
# Например:
nano /etc/nginx/sites-enabled/default
# или
nano /etc/nginx/conf.d/tghub.conf
```

Найди блок:
```nginx
location /hub/ {
    alias /opt/tg-hub/hub/;
    index index.html;
}
```

Замени на (добавь 3 строки с add_header):
```nginx
location /hub/ {
    alias /opt/tg-hub/hub/;
    index index.html;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    add_header Expires "0";
}
```

Сохрани: `Ctrl+O`, Enter, `Ctrl+X`.

## 4. Проверь и перезагрузи nginx
```bash
sudo nginx -t
sudo systemctl reload nginx
```

Если `nginx -t` показал "syntax is ok" — готово.
