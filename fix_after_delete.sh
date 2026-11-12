#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470
AU=(--cluster-user=dgek --cluster-pwd=<CLUSTER_PASSWORD>)
HBA=/var/lib/pgpro/1c-16/data/pg_hba.conf
BAK=/root/pg_hba.conf.bak.gonch
PSQL="su -s /bin/bash postgres -c"

echo "=== 1. удаляю лишнюю инфобазу montesbuh (БД оставляю) ==="
U=$(timeout 15 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^infobase/{u=$2} /^name/{if($2=="montesbuh"){print u; exit}}')
if [ -n "${U:-}" ]; then
  timeout 25 $RAC 127.0.0.1:1545 infobase drop --cluster=$C --infobase=$U "${AU[@]}" 2>&1 | tail -1 | sed 's/^/  /'
else
  echo "  инфобазы montesbuh нет"
fi

echo "=== 2. trust для usr_goncharov + перезапуск 1С ==="
cp "$HBA" "$BAK"
awk 'NR==1{print "host    all             usr_goncharov    127.0.0.1/32            trust"} {print}' "$BAK" > "$HBA"
chown postgres:postgres "$HBA"; chmod 600 "$HBA"
$PSQL "psql -c 'select pg_reload_conf()'" >/dev/null 2>&1
systemctl stop srv1cv8 ras.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost' 2>/dev/null
sleep 4
systemctl start srv1cv8
sleep 35
systemctl start ras.service 2>/dev/null
sleep 10
echo "  srv1cv8: $(systemctl is-active srv1cv8) | ras: $(systemctl is-active ras.service)"

echo "=== 3. новый пароль роли + запись в инфобазу ==="
PW=$(openssl rand -hex 12)
$PSQL "psql -c \"alter role usr_goncharov password '$PW'\"" >/dev/null 2>&1 && echo "  пароль роли обновлён"
UG=$(timeout 15 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^infobase/{u=$2} /^name/{if($2=="goncharov"){print u; exit}}')
echo "  uuid: ${UG:-нет}"
timeout 25 $RAC 127.0.0.1:1545 infobase update --cluster=$C --infobase=$UG --db-user=usr_goncharov --db-pwd="$PW" "${AU[@]}" 2>&1 | tail -1 | sed 's/^/  update: /'
sleep 3

echo "=== 4. возвращаю pg_hba ==="
cp "$BAK" "$HBA"; chown postgres:postgres "$HBA"; chmod 600 "$HBA"
$PSQL "psql -c 'select pg_reload_conf()'" >/dev/null 2>&1 && echo "  pg_hba восстановлен"

echo "=== 5. проверка ==="
sleep 3
echo "  страница goncharov: $(curl -s --max-time 30 http://127.0.0.1:8081/WEB/goncharov/ru_RU/ | wc -c) байт"
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
