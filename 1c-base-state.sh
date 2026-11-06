#!/bin/bash
# Проверяет наличие информационных баз в кластере 1С.
# Использование: 1c-base-state <имя> [имя...]
# Вывод: «<имя> yes|no», по строке на базу.
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}

[ $# -ge 1 ] || { echo "usage: 1c-base-state <name> [name...]"; exit 64; }

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || exit 2

LIST=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" 2>/dev/null | awk -F' *: *' '/^name/{print $2}')

for NAME in "$@"; do
  if echo "$LIST" | grep -qx "$NAME"; then
    echo "$NAME yes"
  else
    echo "$NAME no"
  fi
done
