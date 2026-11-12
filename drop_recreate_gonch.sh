#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470
AU=(--cluster-user=dgek --cluster-pwd=<CLUSTER_PASSWORD>)
HBA=/var/lib/pgpro/1c-16/data/pg_hba.conf
U=7ce767a0-34a1-483c-b553-f643bd9d7757

echo "=== 1. временно доверяем usr_goncharov с localhost ==="
cp "$HBA" "$HBA.bak.$(date +%H%M)"
awk 'NR==1{print "host    all             usr_goncharov    127.0.0.1/32            trust"} {print}' "$HBA.bak.$(date +%H%M)" > "$HBA"
chown postgres:postgres "$HBA"; chmod 600 "$HBA"
su -s /bin/bash postgres -c "psql -c 'select pg_reload_conf()'" >/dev/null 2>&1 && echo "  pg_hba перезагружен"
sleep 2

echo "=== 2. удаление инфобазы goncharov ==="
timeout 40 $RAC 127.0.0.1:1545 infobase drop --cluster=$C --infobase=$U "${AU[@]}" 2>&1 | tail -2 | sed 's/^/  /'
sleep 3

echo "=== 3. возвращаем pg_hba ==="
cp "$HBA.bak.$(date +%H%M)" "$HBA" 2>/dev/null || true
su -s /bin/bash postgres -c "psql -c 'select pg_reload_conf()'" >/dev/null 2>&1 && echo "  pg_hba восстановлен"

echo "=== 4. создание инфобазы заново ==="
PW=$(openssl rand -hex 12)
su -s /bin/bash postgres -c "psql -c \"alter role usr_goncharov password '$PW'\"" >/dev/null 2>&1
su -s /bin/bash postgres -c "psql -d goncharov -c \"REASSIGN OWNED BY postgres TO usr_goncharov\"" >/dev/null 2>&1
su -s /bin/bash postgres -c "psql -d goncharov -c \"GRANT ALL ON SCHEMA public TO usr_goncharov\"" >/dev/null 2>&1
timeout 30 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name=goncharov \
  --dbms=PostgreSQL --db-server=127.0.0.1 --db-name=goncharov --db-user=usr_goncharov \
  --db-pwd="$PW" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -2 | sed 's/^/  /'
sleep 3
echo "=== 5. проверка ==="
echo "  страница: $(curl -s --max-time 30 http://127.0.0.1:8081/WEB/goncharov/ | wc -c) байт"
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
