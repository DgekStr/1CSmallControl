#!/bin/bash
# Применяет настройки подключения из /etc/1c-portal/settings.json:
# хост сервера 1С в публикации (default.vrd) и имя хоста Apache для портала.
set -uo pipefail

JSON=/etc/1c-portal/settings.json
[ -f "$JSON" ] || { echo "нет файла настроек"; exit 1; }

python3 - "$JSON" <<'PY'
import json
import re
import sys

conf_path = "/etc/apache2/sites-available/1c-portal.conf"
vrd_dir = "/var/www/1c"

data = json.load(open(sys.argv[1], encoding="utf-8"))
ic_host = (data.get("ic_host") or "").strip()
server_name = (data.get("portal_server_name") or "").strip()
base_map = data.get("bases") or {}

# 1) публикация 1С: адрес кластера
import glob
for vrd in glob.glob(vrd_dir + "/*/default.vrd"):
    text = open(vrd, encoding="utf-8").read()
    slug = vrd.split("/")[-2]
    ref = base_map.get(slug) or slug
    new_ib = 'ib="Srvr=%s;Ref=%s;"' % (ic_host or "localhost", ref)
    updated, n = re.subn(r'ib="[^"]*"', new_ib, text, count=1)
    if n:
        open(vrd, "w", encoding="utf-8").write(updated)
        print("  публикация %s -> %s" % (slug, new_ib))

# 2) Apache: имя портала и разрешение любых хостов
if server_name:
    text = open(conf_path, encoding="utf-8").read()
    text = re.sub(r"^\s*ServerName\s+.*$", "    ServerName %s" % server_name, text, count=1, flags=re.M)
    if not re.search(r"^\s*ServerAlias\s", text, flags=re.M):
        text = re.sub(r"^(\s*ServerName\s+.*)$", r"\1\n    ServerAlias *", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^\s*ServerAlias\s+.*$", "    ServerAlias *", text, count=1, flags=re.M)
    open(conf_path, "w", encoding="utf-8").write(text)
    print("  Apache: ServerName %s, ServerAlias *" % server_name)

# адрес для bash-части (ragent -host)
try:
    open("/etc/1c-portal/.ic-host", "w", encoding="utf-8").write(ic_host or "")
except OSError:
    pass
PY

# 3) адрес, который кластер 1С объявляет клиентам (реестр кластера + ragent)
UNIT=/etc/systemd/system/srv1cv8.service
IC_HOST=$(cat /etc/1c-portal/.ic-host 2>/dev/null)
if [ -n "$IC_HOST" ]; then
  CUR_HOST=$(grep -oP '(?<=-host )\S+' "$UNIT" 2>/dev/null | head -1)
  if [ "$CUR_HOST" != "$IC_HOST" ]; then
    cp "$UNIT" "$UNIT.bak.$(date +%Y%m%d%H%M%S)"
    sed -i "s/-host $CUR_HOST/-host $IC_HOST/" "$UNIT"
    systemctl daemon-reload
  fi
  /usr/local/bin/1c-set-cluster-host "$IC_HOST"
fi

# 4) учётные данные администратора PostgreSQL — в файл, доступный только root
mkdir -p /etc/1c-portal
PASS_TMP=/etc/1c-portal/.pg-pass
PG_CONF=/etc/1c-portal/pg-admin.conf
PG_USER=$(python3 -c "import json,sys; print(json.load(open('$JSON', encoding='utf-8')).get('pg_admin_user') or 'postgres')" 2>/dev/null)
if [ -f "$PASS_TMP" ]; then
  PG_PASS=$(cat "$PASS_TMP")
  umask 077
  {
    echo "# учётные данные администратора PostgreSQL (создано порталом)"
    echo "PG_ADMIN_USER=$PG_USER"
    echo "PG_ADMIN_PASSWORD=$PG_PASS"
  } > "$PG_CONF"
  chmod 600 "$PG_CONF"
  shred -u "$PASS_TMP" 2>/dev/null || rm -f "$PASS_TMP"
  echo "  учётные данные PostgreSQL сохранены"
fi

if apache2ctl configtest >/dev/null 2>&1; then
  systemctl reload apache2
  echo "настройки применены, Apache перезагружен"
else
  apache2ctl configtest 2>&1 | tail -2
  echo "ОШИБКА в конфигурации Apache — изменения не применены"
  exit 2
fi
