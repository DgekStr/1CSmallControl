#!/bin/bash
# Управление блокировкой регламентных заданий информационной базы.
# Использование: 1c-jobs-deny <имя_базы> on|off
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}

NAME="${1:-}"
STATE="${2:-}"
case "$STATE" in
  on|off) ;;
  toggle)
    CLUSTER0=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
    CUR0=$($RAC "$RAS" infobase info --cluster="${CLUSTER0:-}" --name="$NAME" \
            --infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}" 2>/dev/null \
            | awk -F' *: *' '/^scheduled-jobs-deny/{print $2; exit}')
    if [ "$CUR0" = "on" ]; then STATE=off; else STATE=on; fi
    ;;
  *) echo "usage: 1c-jobs-deny <name> on|off|toggle"; exit 64 ;;
esac

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || { echo "кластер недоступен"; exit 2; }

OUT=$($RAC "$RAS" infobase update --cluster="$CLUSTER" --name="$NAME" \
        --infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}" \
        --scheduled-jobs-deny="$STATE" 2>&1)
if echo "$OUT" | grep -qiE 'error|ошиб|not found|не найд'; then
  echo "не удалось изменить состояние: $(echo "$OUT" | head -2 | tr '\n' ' ')"
  exit 3
fi

CUR=$($RAC "$RAS" infobase info --cluster="$CLUSTER" --name="$NAME" \
        --infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}" 2>/dev/null \
        | awk -F' *: *' '/^scheduled-jobs-deny/{print $2; exit}')

if [ "$CUR" = "on" ]; then
  echo "регламентные задания заблокированы ($NAME)"
else
  echo "регламентные задания включены ($NAME)"
fi
