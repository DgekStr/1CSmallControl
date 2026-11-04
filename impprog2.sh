#!/bin/bash
DB=dgek
q() { su -s /bin/bash postgres -c "psql -Atc \"$1\"" 2>/dev/null; }

echo "размер сейчас: $(q "select pg_size_pretty(pg_database_size('$DB'))")"
S1=$(q "select pg_database_size('$DB')"); sleep 15; S2=$(q "select pg_database_size('$DB')")
echo "прирост за 15 с: $(( (S2 - S1) / 1024 )) КБ"

echo
echo "=== активные запросы (state=active) ==="
su -s /bin/bash postgres -c "psql -c \"select pid, state, wait_event_type, wait_event, date_trunc('second', now()-query_start) as dur, left(regexp_replace(query,'\\s+',' ','g'),60) as q from pg_stat_activity where datname='$DB' and state='active' order by query_start limit 8\"" 2>/dev/null

echo
echo "=== число таблиц в базе (растёт по ходу загрузки) ==="
q "select count(*) from information_schema.tables where table_schema='public'"

echo
echo "=== сеансы пользователя (не фоновые) ==="
/opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 session list --cluster=e3220a07-7374-4fc0-b4fb-25ace3789930 2>/dev/null | grep -A3 'app-id' | grep -vE 'SystemBackgroundJob|^\-\-$' | head -12
