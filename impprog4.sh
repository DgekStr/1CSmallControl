#!/bin/bash
P() { su -s /bin/bash postgres -c "psql -Atc \"$1\"" 2>/dev/null; }
S1=$(P "select pg_database_size('dgek')")
Q1=$(P "select left(regexp_replace(query,'\s+',' ','g'),60) from pg_stat_activity where datname='dgek' and state='active' limit 1")
sleep 30
S2=$(P "select pg_database_size('dgek')")
Q2=$(P "select left(regexp_replace(query,'\s+',' ','g'),60) from pg_stat_activity where datname='dgek' and state='active' limit 1")
echo "размер: $(P "select pg_size_pretty(pg_database_size('dgek'))")"
echo "прирост за 30 с: $(( (S2 - S1) / 1048576 )) МБ ($(( (S2 - S1) / 30720 )) КБ/с)"
echo "активные сессии: $(P "select count(*) from pg_stat_activity where datname='dgek' and state='active'")"
echo "операция сейчас: $Q2"
echo "операция 30 с назад: $Q1"
