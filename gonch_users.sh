#!/bin/bash
set -uo pipefail
P() { su -s /bin/bash postgres -c "$1"; }
DUMP=/mnt/1cbackup/goncharov-20261111-1235.dump

echo "=== 1. восстанавливаю дамп 11.11 в отдельную БД ==="
P "psql -c 'drop database if exists gonch_tmp with (force)'" >/dev/null 2>&1
P "psql -c 'create database gonch_tmp'" >/dev/null 2>&1
P "pg_restore -j 4 --no-owner --no-privileges -d gonch_tmp $DUMP" 2>&1 | grep -cE 'ошибка|error' | sed 's/^/  ошибок восстановления: /'
echo "  пользователей в восстановленном дампе: $(P "psql -d gonch_tmp -Atc \"select count(*) from v8users\"" 2>/dev/null)"
P "psql -d gonch_tmp -Atc \"select name from v8users order by 1\"" 2>/dev/null | head -12 | sed 's/^/    /'

echo "=== 2. переношу v8users в goncharov ==="
P "psql -d gonch_tmp -c \"\\copy (select * from v8users) to '/tmp/v8g.txt'\"" >/dev/null 2>&1
echo "  выгружено: $(wc -l < /tmp/v8g.txt 2>/dev/null || echo 0) строк"
P "psql -d goncharov -c 'delete from v8users'" 2>&1 | tail -1 | sed 's/^/  /'
P "psql -d goncharov -c \"\\copy v8users from '/tmp/v8g.txt'\"" 2>&1 | tail -1 | sed 's/^/  /'
echo "  стало: $(P "psql -d goncharov -Atc \"select count(*) from v8users\"" 2>/dev/null) пользователей"

echo "=== 3. добавляю dgek с админом ==="
P "psql -d test -c \"\\copy (select * from v8users where name='dgek') to '/tmp/dg.txt'\"" >/dev/null 2>&1
P "psql -d goncharov -c \"\\copy v8users from '/tmp/dg.txt'\"" 2>&1 | tail -1 | sed 's/^/  /'
P "psql -d goncharov -c \"update v8users set admrole=true where name='dgek'\"" 2>&1 | tail -1 | sed 's/^/  /'

echo "=== 4. итог ==="
P "psql -d goncharov -Atc \"select name from v8users order by 1\"" 2>/dev/null | sed 's/^/  /'
P "psql -c 'drop database if exists gonch_tmp with (force)'" >/dev/null 2>&1
echo "  страница: $(curl -s --max-time 25 http://127.0.0.1:8081/WEB/goncharov/ru_RU/ | wc -c) байт"
