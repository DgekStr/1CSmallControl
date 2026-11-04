#!/bin/bash
# Установка портала 1С на Ubuntu 22.04 / 24.04.
# Flask + SQLite, отдаётся gunicorn'ом за Apache (mod_proxy).
#
# Переменные окружения (все необязательные):
#   PORTAL_SERVER_NAME  — домен/IP сайта (по умолчанию portal.example.ru)
#   PORTAL_SITE_NAME    — имя сервиса и конфига Apache (по умолчанию 1c-portal)
#   PORTAL_ADMIN_PASSWORD — пароль администратора при первичной инициализации
#                           (если не задан — будет сгенерирован и напечатан)
#   PORTAL_IC_HOST      — сервер 1С в инструкции по Конфигуратору
#   PORTAL_SUPPORT_NAME / PORTAL_SUPPORT_URL — блок «Нужна помощь с платформой?»
set -eu

APP_DIR=/opt/1c-portal
SITE=${PORTAL_SITE_NAME:-1c-portal}
SERVER_NAME=${PORTAL_SERVER_NAME:-portal.example.ru}
BIND=127.0.0.1:8080

echo "=== 1/5 пакеты ==="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-flask gunicorn >/dev/null

echo "=== 2/5 файлы ==="
mkdir -p "$APP_DIR"
cp -r app.py templates static "$APP_DIR"/
if [ ! -f "$APP_DIR/.secret_key" ]; then
  head -c 32 /dev/urandom | base64 > "$APP_DIR/.secret_key"
fi
chmod 600 "$APP_DIR/.secret_key"
chown -R www-data:www-data "$APP_DIR"

echo "=== 3/5 база ==="
su -s /bin/bash www-data -c "cd $APP_DIR && PORTAL_DB=$APP_DIR/portal.db python3 -c 'import app'"
ls -la "$APP_DIR/portal.db"

echo "=== 4/5 systemd ==="
cat > "/etc/systemd/system/${SITE}.service" <<EOS
[Unit]
Description=1C access portal (Flask)
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
Environment=PORTAL_DB=$APP_DIR/portal.db
Environment=PORTAL_VERSION=${PORTAL_VERSION:-1.3}
Environment=PORTAL_IC_HOST=${PORTAL_IC_HOST:-1c.example.ru}
Environment=PORTAL_SUPPORT_NAME=${PORTAL_SUPPORT_NAME:-example.ru}
Environment=PORTAL_SUPPORT_URL=${PORTAL_SUPPORT_URL:-https://example.ru/contacts.html}
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/gunicorn --worker-class gthread --workers 2 --threads 8 --bind $BIND --timeout 900 app:app
Restart=always
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable --now "${SITE}.service"

echo "=== 5/5 apache ==="
a2enmod proxy proxy_http >/dev/null

# Публикации 1С: отдельный каталог, подключаемый только внутренним vhost'ом.
mkdir -p /etc/apache2/1c-publications
cat > /etc/apache2/sites-available/1c-internal.conf <<EOS
Listen 127.0.0.1:8081

<VirtualHost 127.0.0.1:8081>
    ServerName 1c-internal
    DocumentRoot /var/www/html

    # публикации 1С доступны только изнутри сервера
    IncludeOptional /etc/apache2/1c-publications/*.conf

    ErrorLog \${APACHE_LOG_DIR}/1c-internal-error.log
    CustomLog \${APACHE_LOG_DIR}/1c-internal-access.log combined
</VirtualHost>
EOS
a2ensite 1c-internal >/dev/null

cat > "/etc/apache2/sites-available/${SITE}.conf" <<EOS
<VirtualHost *:80>
    ServerName $SERVER_NAME
    DocumentRoot /var/www/html

    ProxyPreserveHost On

    # публикации 1С — только через портал: он проверяет сессию и право на базу
    ProxyPass /WEB/ http://$BIND/WEB/

    ProxyPass / http://$BIND/ retry=0
    ProxyPassReverse / http://$BIND/

    ErrorLog \${APACHE_LOG_DIR}/${SITE}-error.log
    CustomLog \${APACHE_LOG_DIR}/${SITE}-access.log combined
</VirtualHost>
EOS
a2ensite "$SITE" >/dev/null
a2dissite 000-default >/dev/null 2>&1 || true
apache2ctl configtest
systemctl reload apache2

echo
echo "Готово. Портал: http://$SERVER_NAME/"
echo "Логин администратора: admin (пароль — см. вывод инициализации БД)"
