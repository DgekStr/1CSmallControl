#!/bin/bash
# 1c-verify-base <имя_инфобазы> <имя_БД_PostgreSQL> <роль_БД>
# Приводит пароль роли и запись в кластере в согласованное состояние.
# Трогает ТОЛЬКО указанную инфобазу.
set -uo pipefail
NAME=${1:?usage: 1c-verify-base <ib> <db> <role>}
DB=${2:?}
ROLE=${3:?}

CONF=/etc/1c-portal/1c-session-admin.conf
[ -r "$CONF" ] && . "$CONF"
RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CLUSTER=${IC_CLUSTER:-}
CA=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")
[ -n "$CLUSTER" ] || { echo "нет IC_CLUSTER"; exit 2; }

run_rac() { timeout 20 "$RAC" "$RAS" "$@" --cluster="$CLUSTER" "${CA[@]}"; }

IB=$(run_rac infobase summary list 2>/dev/null | awk -F' *: *' -v w="$NAME" '/^infobase /{u=$2} /^name /{if($2==w){print u; exit}}')
if [ -z "${IB:-}" ]; then
  echo "инфобаза «$NAME» не найдена в кластере — пропуск проверки"
  exit 0
fi

PW=$(openssl rand -hex 12)
if ! su -s /bin/bash postgres -c "psql -c \"alter role $ROLE password '$PW'\"" >/dev/null 2>&1; then
  echo "не удалось сменить пароль роли $ROLE"
  exit 3
fi

# освобождаем инфобазу от соединений, меняем пароль, возвращаем режим
run_rac infobase update --infobase="$IB" --sessions-deny=yes --scheduled-jobs-deny=yes >/dev/null 2>&1
for i in 1 2 3; do
  for s in $(run_rac session list --infobase="$IB" 2>/dev/null | grep -E '^session ' | awk '{print $3}'); do
    timeout 10 "$RAC" "$RAS" session terminate --cluster="$CLUSTER" --session="$s" "${CA[@]}" >/dev/null 2>&1
  done
  sleep 3
done
OUT=$(run_rac infobase update --infobase="$IB" --db-user="$ROLE" --db-pwd="$PW" 2>&1 | tail -1)
run_rac infobase update --infobase="$IB" --sessions-deny=no --scheduled-jobs-deny=no >/dev/null 2>&1

if su -s /bin/bash postgres -c "PGPASSWORD='$PW' psql -h 127.0.0.1 -U '$ROLE' -d '$DB' -Atc 'select 1'" >/dev/null 2>&1; then
  echo "проверка подключения «$NAME» → $DB: ok"
  exit 0
fi
echo "проверка подключения «$NAME» → $DB: НЕ УДАЛАСЬ ${OUT:-}"
exit 1
