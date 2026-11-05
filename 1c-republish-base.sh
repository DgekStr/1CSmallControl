#!/bin/bash
# Пересоздаёт публикацию 1С для одной базы: default.vrd и конфиг Apache.
# Использование: 1c-republish-base <код_базы> [имя_базы_в_БД]
set -uo pipefail

SLUG="${1:-}"
DBNAME="${2:-$SLUG}"
[ -n "$SLUG" ] || { echo "usage: 1c-republish-base <slug> [db_name]"; exit 64; }

SETTINGS=/etc/1c-portal/settings.json
HOST=$(python3 -c "import json;print(json.load(open('$SETTINGS', encoding='utf-8')).get('ic_host') or 'localhost')" 2>/dev/null)
HOST=${HOST:-localhost}

VDIR="/var/www/1c/$SLUG"
VRD="$VDIR/default.vrd"
CONF="/etc/apache2/1c-publications/1c-$SLUG-web.conf"

mkdir -p "$VDIR"

cat > "$VRD" <<VRDEOF
<?xml version="1.0" encoding="UTF-8"?>
<point xmlns="http://v8.1c.ru/8.2/virtual-resource-system"
		xmlns:xs="http://www.w3.org/2001/XMLSchema"
		xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
		base="/WEB/$SLUG"
		ib="Srvr=$HOST;Ref=$DBNAME;">
	<ws pointEnableCommon="true"/>
	<standardOdata enable="false"
			reuseSessions="autouse"
			sessionMaxAge="20"
			poolSize="10"
			poolTimeout="5"/>
	<analytics enable="true"
			sessionMaxAge="1200"
			poolSize="500"
			poolTimeout="5"/>
</point>
VRDEOF
chown www-data:www-data "$VRD" 2>/dev/null || true

cat > "$CONF" <<CONFEOF

# 1c publication
Alias "/WEB/$SLUG" "$VDIR/"
<Directory "$VDIR/">
    AllowOverride All
    Options None
    Require all granted
    SetHandler 1c-application
    ManagedApplicationDescriptor "$VRD"
</Directory>
CONFEOF

if apache2ctl configtest >/dev/null 2>&1; then
  systemctl reload apache2
  echo "публикация $SLUG пересоздана: Srvr=$HOST;Ref=$DBNAME"
else
  apache2ctl configtest 2>&1 | tail -2
  echo "ОШИБКА конфигурации Apache — публикация не применена"
  exit 2
fi
