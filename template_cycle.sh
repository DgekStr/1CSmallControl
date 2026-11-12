#!/bin/bash
set -uo pipefail
P() { su -s /bin/bash postgres -c "$1"; }
TPL=/etc/1c-portal/template-users.txt

echo "=== 1. фиксирую эталонных пользователей из goncharov ==="
P "psql -d goncharov -c \"\\copy (select * from v8users where name in ('Бухгалтер','dgek','Евгений')) to '$TPL'\"" >/dev/null 2>&1
chmod 640 "$TPL"; chown root:www-data "$TPL"
echo "  строк в эталоне: $(wc -l < $TPL 2>/dev/null || echo 0)"
echo "  состав: $(P "psql -d goncharov -Atc \"select string_agg(name::text,', ') from v8users where name in ('Бухгалтер','dgek','Евгений')\"" 2>/dev/null)"

echo "=== 2. снимаю дамп демо-базы test ==="
DUMP=/mnt/1cbackup/demo-test-$(date +%Y%m%d-%H%M).dump
P "pg_dump -Fc -d test -f $DUMP" 2>/dev/null && echo "  дамп: $DUMP ($(du -h $DUMP | cut -f1))"

echo "=== 3. полный цикл: новая БД из дампа + эталонные юзеры ==="
P "psql -c 'drop database if exists tmpl_cycle with (force)'" >/dev/null 2>&1
P "psql -c 'create database tmpl_cycle'" >/dev/null 2>&1
P "pg_restore -j 2 --no-owner --no-privileges -d tmpl_cycle $DUMP" 2>&1 | grep -cE 'ошибка|error' | sed 's/^/  ошибок: /'
echo "  пользователей после восстановления дампа: $(P "psql -d tmpl_cycle -Atc \"select count(*) from v8users\"" 2>/dev/null)"
P "psql -d tmpl_cycle -c 'delete from v8users'" >/dev/null 2>&1
P "psql -d tmpl_cycle -c \"\\copy v8users from '$TPL'\"" 2>&1 | tail -1 | sed 's/^/  эталон: /'
echo "  пользователей после эталона: $(P "psql -d tmpl_cycle -Atc \"select count(*) from v8users\"" 2>/dev/null)"
P "psql -d tmpl_cycle -Atc \"select name from v8users order by 1\"" 2>/dev/null | sed 's/^/    /'
P "psql -c 'drop database if exists tmpl_cycle with (force)'" >/dev/null 2>&1
echo "=== 4. готово ==="
