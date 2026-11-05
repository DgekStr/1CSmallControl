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
PY

if apache2ctl configtest >/dev/null 2>&1; then
  systemctl reload apache2
  echo "настройки применены, Apache перезагружен"
else
  apache2ctl configtest 2>&1 | tail -2
  echo "ОШИБКА в конфигурации Apache — изменения не применены"
  exit 2
fi
