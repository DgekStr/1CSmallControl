#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470
AU=(--cluster-user=dgek --cluster-pwd=<CLUSTER_PASSWORD>)
PSQL="su -s /bin/bash postgres -c"
DUMP=/mnt/1cbackup/goncharov-20261111-1235.dump

echo "=== восстановление БД goncharov из дампа 11.11 ==="
ls -lh "$DUMP" | awk '{print "  дамп:", $5}'
$PSQL "psql -c \"create database goncharov owner usr_goncharov\"" 2>&1 | tail -1 | sed 's/^/  /'
su -s /bin/bash postgres -c "pg_restore -j 4 --no-owner --no-privileges -d goncharov $DUMP" 2>&1 | tail -2 | sed 's/^/  /'
$PSQL "psql -d goncharov -c \"REASSIGN OWNED BY postgres TO usr_goncharov\"" >/dev/null 2>&1
$PSQL "psql -d goncharov -c \"GRANT ALL ON SCHEMA public TO usr_goncharov\"" >/dev/null 2>&1
$PSQL "psql -c \"alter database goncharov owner to usr_goncharov\"" >/dev/null 2>&1
echo "  размер: $($PSQL "psql -Atc \"select pg_size_pretty(pg_database_size('goncharov'))\"" 2>/dev/null)"

echo "=== новый пароль роли и создание инфобазы ==="
PW=$(openssl rand -hex 12)
$PSQL "psql -c \"alter role usr_goncharov password '$PW'\"" >/dev/null 2>&1
timeout 30 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name=goncharov \
  --dbms=PostgreSQL --db-server=127.0.0.1 --db-name=goncharov --db-user=usr_goncharov \
  --db-pwd="$PW" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -2 | sed 's/^/  /'
sleep 4
echo "  страница: $(curl -s --max-time 30 http://127.0.0.1:8081/WEB/goncharov/ru_RU/ | wc -c) байт"
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
