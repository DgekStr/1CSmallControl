#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
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
CA=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")
# для infobase info нужен администратор самой ИБ
IBA=(--infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}")

if [ $# -lt 1 ]; then
  echo "usage: 1c-sessions-count <name> [name...]"
  exit 64
fi

CLUSTER=${IC_CLUSTER:-$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')}
[ -n "$CLUSTER" ] || exit 2

# карта имя инфобазы → uuid
MAP=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null \
      | awk -F' *: *' '/^infobase /{u=$2} /^name /{if (u!="") {print $2"|"u; u=""}}')

# один раз забираем список сеансов и раскладываем по инфобазам
SESS=$($RAC "$RAS" session list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null)

for NAME in "$@"; do
  UUID=$(printf '%s\n' "$MAP" | awk -F'|' -v n="$NAME" '$1==n {print $2; exit}')
  if [ -z "$UUID" ]; then
    echo "$NAME 0 off"
    continue
  fi
  JOBS=$($RAC "$RAS" infobase info --cluster="$CLUSTER" --infobase="$UUID" "${CA[@]}" "${IBA[@]}" 2>/dev/null \
         | awk -F' *: *' '/^scheduled-jobs-deny/{print $2; exit}')
  [ -n "$JOBS" ] || JOBS="off"
  N=$(printf '%s\n' "$SESS" | awk -F' *: *' -v ib="$UUID" '
        /^session /{s=$2}
        /^infobase /{i=$2}
        /^app-id /{a=$2}
        /^user-name /{u=$2}
        /^$/{
          if (s != "" && i == ib && a != "BackgroundJob" && u != "DefUser") c++
          s=""; i=""; a=""; u=""
        }
        END{ if (s != "" && i == ib && a != "BackgroundJob" && u != "DefUser") c++; print c+0 }')
  echo "$NAME ${N:-0} $JOBS"
done
