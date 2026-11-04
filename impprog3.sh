#!/bin/bash
P() { su -s /bin/bash postgres -c "psql -Atc \"$1\"" 2>/dev/null; }
echo "размер:            $(P "select pg_size_pretty(pg_database_size('dgek'))")"
echo "активных сессий:   $(P "select count(*) from pg_stat_activity where datname='dgek' and state='active'")"
echo "всего сессий:      $(P "select count(*) from pg_stat_activity where datname='dgek'")"
echo "таблиц в схеме:    $(P "select count(*) from information_schema.tables where table_schema='public'")"
echo
echo "недавние операции:"
P "select left(regexp_replace(query,'\s+',' ','g'),70) from pg_stat_activity where datname='dgek' and state='active' order by query_start limit 5" | sed 's/^/  /'
echo
echo "=== процессы 1С ==="
ps -eo etime,pcpu,rss,comm --sort=-pcpu | grep -E 'rphost|ragent|rmngr' | head -3
