#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Создаёт пустую серверную базу 1С: роль и база PostgreSQL, информационная база
# в кластере, публикация для портала. Данные загружаются позже из .dt через Конфигуратор.
# Использование: 1c-create-base <код_базы> [имя_базы_в_БД]
set -uo pipefail

NAME="${1:-}"
DB="${2:-$NAME}"
[ -n "$NAME" ] || { echo "usage: 1c-create-base <slug> [db_name]"; exit 64; }

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CA=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")

CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || { echo "кластер 1С недоступен"; exit 2; }

# уже есть в кластере?
EXISTS=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null | grep -c "name     : $NAME")
if [ "$EXISTS" -gt 0 ]; then
  echo "база $NAME уже есть в кластере"
  /usr/local/bin/1c-republish-base "$NAME" "$DB" >/dev/null 2>&1 || true
  echo "публикация обновлена"
  exit 0
fi

ROLE="usr_${DB//[^a-zA-Z0-9_]/_}"
PWD=$(openssl rand -hex 12)

echo "  [1/3] роль PostgreSQL $ROLE"
# 1С создаёт C-функции, поэтому роль должна быть суперпользователем (штатная практика 1С)
# pg_hba использует md5 — пароль роли тоже должен быть в md5
su -s /bin/bash postgres -c "psql -Atc \"select 1 from pg_roles where rolname='$ROLE'\"" 2>/dev/null | grep -q 1 && \
  su -s /bin/bash postgres -c "psql -c \"set password_encryption='md5'; alter role $ROLE login createdb superuser password '$PWD'\"" >/dev/null 2>&1 || \
  su -s /bin/bash postgres -c "psql -c \"set password_encryption='md5'; create role $ROLE login createdb superuser password '$PWD'\"" >/dev/null 2>&1 || \
  { echo "не удалось создать роль"; exit 3; }

echo "  [2/3] информационная база в кластере"
OUT=$($RAC "$RAS" infobase create --cluster="$CLUSTER" --name="$NAME" \
        --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$DB" \
        --db-user="$ROLE" --db-pwd="$PWD" --locale=ru_RU --create-database \
        --license-distribution=allow "${CA[@]}" 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "не удалось создать базу (код $RC): $(echo "$OUT" | head -2 | tr '\n' ' ')"
  exit 4
fi

if ! $RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null | grep -q "name     : $NAME"; then
  echo "база не появилась в кластере: $(echo "$OUT" | head -2 | tr '\n' ' ')"
  exit 5
fi

echo "  [3/3] публикация"
/usr/local/bin/1c-republish-base "$NAME" "$DB" | sed 's/^/    /'

echo "готова пустая база $NAME — загрузите данные через Конфигуратор (.dt)"