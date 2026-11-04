#!/bin/bash
# Отключение всех сеансов от информационной базы 1С.
# Использование: 1c-kick-sessions [--dry] <имя_базы>
#
# Учётные данные администратора ИБ берутся из /etc/1c-portal/1c-session-admin.conf
# (строки IC_ADMIN_USER=... и IC_ADMIN_PWD=...), файл доступен только root.
set -uo pipefail

DRY=0
if [ "${1:-}" = "--dry" ]; then DRY=1; shift; fi

NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "usage: 1c-kick-sessions [--dry] <infobase-name>"
  exit 64
fi

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
if [ -z "$CLUSTER" ]; then
  echo "не удалось получить идентификатор кластера"
  exit 2
fi

IB=$($RAC "$RAS" infobase info --cluster="$CLUSTER" --name="$NAME" \
      --infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}" 2>/dev/null \
      | awk -F': *' '/^infobase /{print $2; exit}')
if [ -z "$IB" ]; then
  echo "информационная база «$NAME» не найдена или нет прав администратора ИБ"
  exit 3
fi

SESSIONS=$($RAC "$RAS" session list --cluster="$CLUSTER" --infobase="$IB" 2>/dev/null \
      | awk -F': *' '/^session /{print $2}')

COUNT=0
for s in $SESSIONS; do
  [ -n "$s" ] || continue
  COUNT=$((COUNT + 1))
  if [ "$DRY" = "1" ]; then
    echo "  [dry] сеанс $s"
  else
    $RAC "$RAS" session terminate --cluster="$CLUSTER" --session="$s" >/dev/null 2>&1 || true
  fi
done

if [ "$DRY" = "1" ]; then
  echo "сеансов у базы «$NAME»: $COUNT (режим проверки, ничего не отключено)"
else
  echo "отключено сеансов: $COUNT (база «$NAME»)"
fi
