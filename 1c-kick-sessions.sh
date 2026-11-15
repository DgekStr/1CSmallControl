#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# 1c-kick-sessions [--dry] <инфобаза> — завершает все сеансы указанной базы 1С.
#   --dry            только показать сеансы
#   KICK_DENY_SEC=N  на сколько секунд запретить вход (по умолчанию 0).
#                    20 с вешали веб-клиент: он не показывал «сеанс завершён»,
#                    а просто замирал на время запрета. Включайте осознанно.
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
CA=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")
# операции с конкретной инфобазой (в т.ч. запрет сеансов) требуют её администратора
IBA=(--infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}")
DENY_SEC=${KICK_DENY_SEC:-0}

CLUSTER=${IC_CLUSTER:-$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')}
if [ -z "$CLUSTER" ]; then
  echo "не удалось получить идентификатор кластера"
  exit 2
fi

IB=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null \
      | awk -F' *: *' -v w="$NAME" '/^infobase /{u=$2} /^name /{if($2==w){print u; exit}}')
if [ -z "$IB" ]; then
  echo "информационная база «$NAME» не найдена"
  exit 3
fi

# session list: берём сеансы именно этой инфобазы (--infobase не поддерживается)
mapfile -t SESSIONS < <($RAC "$RAS" session list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null \
  | awk -F' *: *' -v ib="$IB" '
      /^session /{s=$2}
      /^infobase /{i=$2}
      /^app-id /{a=$2}
      /^user-name /{u=$2}
      /^$/{
        if (s != "" && i == ib && a != "BackgroundJob") print s
        s=""; i=""; a=""; u=""
      }
      END{ if (s != "" && i == ib && a != "BackgroundJob") print s }')

if [ "$DRY" = "1" ]; then
  if [ ${#SESSIONS[@]} -gt 0 ]; then printf '  сеанс %s\n' "${SESSIONS[@]}"; fi
  echo "сеансов у базы «$NAME»: ${#SESSIONS[@]} (режим проверки, ничего не отключено)"
  exit 0
fi

# 1) короткий запрет входа, чтобы веб-клиент не переподключился мгновенно.
#    Делаем это только если у нас есть права администратора этой ИБ
#    (иначе включить/выключить запрет не сможем — база останется закрытой).
IB_OK=0
if [ -n "$($RAC "$RAS" infobase info --cluster="$CLUSTER" --infobase="$IB" "${CA[@]}" "${IBA[@]}" 2>/dev/null)" ]; then
  IB_OK=1
fi
if [ ${#SESSIONS[@]} -gt 0 ] && [ "$DENY_SEC" -gt 0 ] && [ "$IB_OK" = "1" ]; then
  $RAC "$RAS" infobase update --cluster="$CLUSTER" --infobase="$IB" \
       --sessions-deny=on "${CA[@]}" "${IBA[@]}" >/dev/null 2>&1 || true
  (
    sleep "$DENY_SEC"
    $RAC "$RAS" infobase update --cluster="$CLUSTER" --infobase="$IB" \
         --sessions-deny=off "${CA[@]}" "${IBA[@]}" >/dev/null 2>&1 || true
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

# 2) завершаем сеансы — с учётными данными администратора кластера,
#    иначе rac отвечает «Администратор кластера не аутентифицирован»
OK=0
FAIL=0
FIRST_ERR=''
for s in "${SESSIONS[@]}"; do
  [ -n "$s" ] || continue
  ERR=$($RAC "$RAS" session terminate --cluster="$CLUSTER" --session="$s" "${CA[@]}" 2>&1)
  if [ -z "$ERR" ]; then
    OK=$((OK + 1))
  else
    FAIL=$((FAIL + 1))
    [ -z "$FIRST_ERR" ] && FIRST_ERR=$(printf '%s' "$ERR" | head -1)
  fi
done

echo "отключено сеансов: $OK (база «$NAME»)${FAIL:+, не удалось: $FAIL}"
[ -n "$FIRST_ERR" ] && echo "  ошибка: $FIRST_ERR"
[ "$OK" -gt 0 ] && [ "$DENY_SEC" -gt 0 ] && echo "  вход в базу запрещён на ${DENY_SEC} с, затем откроется снова"
exit 0
