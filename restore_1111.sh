#!/bin/bash
set -uo pipefail
SHARE=/mnt/1cbackup
TS=$(date +%Y%m%d-%H%M)
PSQL="su -s /bin/bash postgres -c"

echo "=== 1. страховочные дампы текущего состояния ==="
for pair in "dgekdb dgekdb" "goncharov goncharov" "montesbuh montesbuh" "test test"; do
  set -- $pair; db=$1
  $PSQL "pg_dump -Fc -d $db -f $SHARE/safety-$db-$TS.dump" 2>/dev/null && echo "  $db: safety-$db-$TS.dump ($(du -h $SHARE/safety-$db-$TS.dump | cut -f1))"
done

echo "=== 2. остановка 1С ==="
systemctl stop srv1cv8 ras.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost' 2>/dev/null
sleep 3
echo "  процессов 1С: $(pgrep -c -f 'ragent|rmngr|rphost' 2>/dev/null || echo 0)"

echo "=== 3. восстановление из дампов 11.11.2026 12:35 ==="
restore() {
  local db=$1 dump=$2 owner=$3
  echo "  --- $db ← $(basename $dump)"
  $PSQL "psql -c \"drop database if exists $db with (force)\"" >/dev/null 2>&1
  $PSQL "psql -c \"create database $db owner $owner\"" >/dev/null 2>&1
  su -s /bin/bash postgres -c "pg_restore -j 4 --no-owner --no-privileges -d $db $dump" 2>&1 | tail -2 | sed 's/^/      /'
  $PSQL "psql -d $db -c \"REASSIGN OWNED BY postgres TO $owner\"" >/dev/null 2>&1
  $PSQL "psql -c \"alter database $db owner to $owner\"" >/dev/null 2>&1
  echo "      размер: $($PSQL "psql -Atc \"select pg_size_pretty(pg_database_size('$db'))\"" 2>/dev/null)"
}
restore dgekdb   "$SHARE/dgek2-20261111-1235.dump"    usr_dgekdb
restore goncharov "$SHARE/goncharov-20261111-1235.dump" usr_goncharov
restore montesbuh "$SHARE/montesbuh-20261111-1235.dump" usr_montesbuh
restore test      "$SHARE/test-20261111-1235.dump"      usr_test

echo "=== 4. запуск 1С ==="
systemctl start srv1cv8
sleep 30
systemctl start ras.service 2>/dev/null
sleep 8
echo "  srv1cv8: $(systemctl is-active srv1cv8) | ras: $(systemctl is-active ras.service)"

echo "=== 5. проверка ==="
for b in dgek-db test goncharov montesbuh; do
  echo "  $b: $(curl -s -o /dev/null -w '%{http_code}' --max-time 25 http://127.0.0.1:8081/WEB/$b/)"
done
echo "  портал: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz)"
