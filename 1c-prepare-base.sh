#!/bin/bash
# Создание пустой серверной базы 1С: роль PostgreSQL + информационная база в кластере
# + публикация в Apache. Данные затем загружаются из .dt средствами Конфигуратора.
# Использование: sudo ./1c-prepare-base.sh <имя_базы>
#
# Переменные: IC_HOST (по умолчанию 1c.example.ru), IC_BIN (каталог платформы).
set -uo pipefail

NAME="${1:?usage: $0 <name>}"
IC_HOST=${IC_HOST:-1c.example.ru}
IC_BIN=${IC_BIN:-/opt/1cv8/x86_64/8.3.27.2342}
RAC=$IC_BIN/rac
WEBINST=$IC_BIN/webinst
RAS=${IC_RAS:-127.0.0.1:1545}

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
DB="ic_${NAME//[^a-zA-Z0-9_]/_}"
ROLE="usr_${DB}"
PWD=$(openssl rand -hex 12)

echo "[1/3] роль $ROLE"
su -s /bin/bash postgres -c "psql -v ON_ERROR_STOP=1 -c \"CREATE ROLE $ROLE LOGIN CREATEDB SUPERUSER PASSWORD '$PWD'\"" \
  || { echo FAIL; exit 2; }

echo "[2/3] информационная база в кластере (БД создаёт 1С)"
$RAC "$RAS" infobase create --cluster="$CLUSTER" --name="$NAME" \
  --dbms=PostgreSQL --db-server="$IC_HOST" --db-name="$DB" --db-user="$ROLE" --db-pwd="$PWD" \
  --locale=ru_RU --create-database || { echo FAIL; exit 3; }

echo "[3/3] публикация"
CONF="/etc/apache2/conf-available/1c-$NAME-web.conf"
touch "$CONF"
PATH=/usr/sbin:/usr/bin:/sbin:/bin $WEBINST -apache24 -wsdir "WEB/$NAME" \
  -dir "/var/www/1c/$NAME" -connstr "Srvr=$IC_HOST;Ref=$NAME;" -confpath "$CONF" \
  || { echo FAIL; exit 4; }
sed -i '/LoadModule _1cws_module/d' "$CONF"
a2enconf "1c-$NAME-web" >/dev/null || true
apache2ctl configtest >/dev/null && systemctl reload apache2 || { echo FAIL; exit 5; }

echo "OK: база $NAME создана (пустая) — загрузите в неё .dt через Конфигуратор"
echo "     публикация: http://$IC_HOST/WEB/$NAME/"
