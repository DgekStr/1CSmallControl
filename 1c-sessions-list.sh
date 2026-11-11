#!/bin/bash
# Список активных сеансов 1С: по строке на сеанс, поля через «|»
# id|пользователь|клиент|компьютер|начало|последняя активность
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CU=${IC_CLUSTER_USER:-}
CP=${IC_CLUSTER_PWD:-}

AUTH=()
[ -n "$CU" ] && AUTH+=("--cluster-user=$CU")
[ -n "$CP" ] && AUTH+=("--cluster-pwd=$CP")

CLUSTER=${IC_CLUSTER:-}
if [ -z "$CLUSTER" ]; then
  CLUSTER=$($RAC "$RAS" cluster list "${AUTH[@]}" 2>/dev/null | awk '/^cluster/{print $3; exit}')
fi
[ -n "$CLUSTER" ] || exit 2

# карта uuid инфобазы → имя (для колонки «База»)
BASE_MAP=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${AUTH[@]}" 2>/dev/null | awk -F' *: *' '
  /^infobase /{u=$2} /^name /{if (u) {print u"|"$2; u=""}}
')

$RAC "$RAS" session list --cluster="$CLUSTER" "${AUTH[@]}" 2>/dev/null | \
  awk -F' +: +' -v map="$BASE_MAP" '
  BEGIN { n=split(map, lines, "\n"); for (i=1; i<=n; i++) { split(lines[i], kv, "|"); if (kv[1] != "") base[kv[1]]=kv[2] } }
  /^session /{sid=$2}
  /^infobase /{ib=$2}
  /^user-name /{user=$2}
  /^app-id /{app=$2}
  /^host /{host=$2}
  /^started-at /{start=$2}
  /^last-active-at /{last=$2; print sid "|" user "|" app "|" host "|" start "|" last "|" (base[ib] != "" ? base[ib] : ib); user=""; app=""; host=""; start=""; last=""; ib=""}
'
