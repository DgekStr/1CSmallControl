# Прокси 1c.dgek.ru (nginx на 192.168.0.15)

HTTPS для портала и веб-клиента 1С завершается на отдельном сервере `192.168.0.15`
(Ubuntu 24.10, nginx 1.26). Дальше запросы идут на `192.168.0.5` (Apache портала).

## Конфигурация

Файл: `/etc/nginx/conf.d/1c.dgek.ru.conf`

```nginx
upstream portal_1c {
    server 192.168.0.5:80;
    keepalive 32;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name 1c.dgek.ru;
    ssl_certificate     /etc/letsencrypt/live/1c.dgek.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/1c.dgek.ru/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://portal_1c;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

## Зачем каждый параметр

| Параметр | Почему |
|---|---|
| `http2 on` | веб-клиент 1С делает 100+ мелких запросов на одну печать; по HTTP/1.1 браузер держит 6 соединений, по HTTP/2 они идут параллельно в одном |
| `upstream portal_1c` + `keepalive 32` | nginx переиспользует соединения с Apache, вместо нового TCP на каждый запрос |
| `proxy_set_header Connection ""` | обязательно вместе с keepalive, иначе соединение закрывается после ответа |
| `proxy_buffering off` | печатные формы и веб-клиент отдаются потоком; с буферизацией окно печати стоит пустым до конца ответа |
| `proxy_read_timeout 120s` | штатный `poll` 1С висит 60 с; при дефолтных 60 с nginx рвал соединение (`upstream timed out`) и клиент переподключался |

## Проверка

```bash
nginx -t && nginx -s reload
```

Протокол в браузере: DevTools → Network → колонка Protocol = `h2`.

История: включено 2026-11-07, бэкап конфига — `/root/1c.dgek.ru.conf.bak.*`.
