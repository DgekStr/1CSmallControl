#!/bin/bash
# Размеры баз в PostgreSQL. Использование: 1c-base-size <db_name> [db_name...]
# Вывод: «<db_name> <размер>», по строке на базу.
set -uo pipefail

[ $# -ge 1 ] || { echo "usage: 1c-base-size <db> [db...]"; exit 64; }

# из службы портала su может не сработать без терминала — используем sudo -u postgres
PSQL="sudo -n -u postgres psql"
$PSQL -Atc 'select 1' >/dev/null 2>&1 || PSQL="su -s /bin/bash postgres -c psql"

for DB in "$@"; do
  case "$PSQL" in
    *"sudo"*) SIZE=$($PSQL -Atc "select pg_size_pretty(pg_database_size('$DB'))" 2>/dev/null) ;;
    *)        SIZE=$(su -s /bin/bash postgres -c "psql -Atc \"select pg_size_pretty(pg_database_size('$DB'))\"" 2>/dev/null) ;;
  esac
  if [ -n "$SIZE" ]; then
    echo "$DB $SIZE"
  fi
done
