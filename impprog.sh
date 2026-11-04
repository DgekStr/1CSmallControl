#!/bin/bash
DB=dgek
q() { su -s /bin/bash postgres -c "psql -Atc \"$1\"" 2>/dev/null; }

echo "=== размер БД: два замера с интервалом 20 c ==="
S1=$(q "select pg_database_size('$DB')")
sleep 20
S2=$(q "select pg_database_size('$DB')")
echo "было: $S1"
echo "стало: $S2"
if [ -n "$S1" ] && [ -n "$S2" ]; then
  D=$((S2 - S1))
  echo "прирост за 20 с: $((D / 1024)) КБ  (~$((D / 20480)) КБ/с)"
  echo "текущий размер: $(q "select pg_size_pretty(pg_database_size('$DB'))")"
fi

echo
echo "=== активность PostgreSQL по базе $DB ==="
su -s /bin/bash postgres -c "psql -c \"select pid, state, coalesce(wait_event_type,'-') as wait_t, coalesce(wait_event,'-') as wait_e, date_trunc('second', now()-query_start) as dur, left(regexp_replace(query,'\\s+',' ','g'),70) as q from pg_stat_activity where datname='$DB' order by query_start\"" 2>/dev/null

echo
echo "=== блокировки ==="
q "select count(*) from pg_locks l join pg_stat_activity a on a.pid=l.pid where a.datname='$DB' and not l.granted" | sed 's/^/ожидающих блокировок: /'

echo
echo "=== процессы 1С ==="
ps -eo pid,etime,pcpu,pmem,rss,args --sort=-pcpu | grep -E 'rphost|ragent|rmngr' | grep -v grep | head -4

echo
echo "=== сеансы кластера ==="
/opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 session list --cluster=e3220a07-7374-4fc0-b4fb-25ace3789930 2>/dev/null | grep -E 'session|app-id|user-name|infobase' | head -12
