#!/bin/bash
# Состояние сеансов и блокировки регламентных заданий по базам.
# Использование: 1c-sessions-count <имя_базы> [имя_базы...]
# Вывод: «<имя> <сеансов> <jobs:on|off>», по строке на базу.
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}

if [ $# -lt 1 ]; then
  echo "usage: 1c-sessions-count <name> [name...]"
  exit 64
fi

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || exit 2

for NAME in "$@"; do
  INFO=$($RAC "$RAS" infobase info --cluster="$CLUSTER" --name="$NAME" \
          --infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}" 2>/dev/null)
  IB=$(echo "$INFO" | awk -F' *: *' '/^infobase /{print $2; exit}')
  JOBS=$(echo "$INFO" | awk -F' *: *' '/^scheduled-jobs-deny/{print $2; exit}')
  [ -n "$JOBS" ] || JOBS="off"
  if [ -z "$IB" ]; then
    echo "$NAME - $JOBS"
    continue
  fi
  N=$($RAC "$RAS" session list --cluster="$CLUSTER" --infobase="$IB" 2>/dev/null | grep -c '^session ')
  echo "$NAME $N $JOBS"
done
