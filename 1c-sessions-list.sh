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

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || exit 2

$RAC "$RAS" session list --cluster="$CLUSTER" 2>/dev/null | awk -F' +: +' '
  /^session /{sid=$2}
  /^user-name /{user=$2}
  /^app-id /{app=$2}
  /^host /{host=$2}
  /^started-at /{start=$2}
  /^last-active-at /{last=$2; print sid "|" user "|" app "|" host "|" start "|" last; user=""; app=""; host=""; start=""; last=""}
'
