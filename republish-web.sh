#!/bin/bash
# Публикация информационных баз 1С в Apache под /WEB/<slug>/ через webinst.
# Использование: sudo ./republish-web.sh <slug> [slug...]
#
# Переменные: IC_HOST (по умолчанию 1c.example.ru), IC_BIN (каталог платформы),
#             IC_WWW (каталог публикаций, по умолчанию /var/www/1c)
set -eu

IC_HOST=${IC_HOST:-1c.example.ru}
IC_BIN=${IC_BIN:-/opt/1cv8/x86_64/8.3.27.2342}
IC_WWW=${IC_WWW:-/var/www/1c}
WEBINST=$IC_BIN/webinst
CONF_DIR=/etc/apache2/conf-available

if [ $# -lt 1 ]; then
  echo "usage: $0 <slug> [slug...]"
  exit 64
fi

for slug in "$@"; do
  echo "--- $slug ---"
  mkdir -p "$IC_WWW/$slug"
  CONF="$CONF_DIR/1c-$slug-web.conf"
  touch "$CONF"
  PATH=/usr/sbin:/usr/bin:/sbin:/bin $WEBINST -apache24 -wsdir "WEB/$slug" \
    -dir "$IC_WWW/$slug" -connstr "Srvr=$IC_HOST;Ref=$slug;" -confpath "$CONF"
  sed -i '/LoadModule _1cws_module/d' "$CONF"
  a2enconf "1c-$slug-web" >/dev/null
done

apache2ctl configtest >/dev/null && systemctl reload apache2
echo "Готово: http://$IC_HOST/WEB/<slug>/"
