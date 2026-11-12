#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470
AU=(--cluster-user=dgek --cluster-pwd=<CLUSTER_PASSWORD>)
PSQL="su -s /bin/bash postgres -c"

fix_ib() {
  local name=$1 dbase=$2 role=$3 uuid=$4
  echo "=== $name ==="
  echo "  запрет сеансов + отключение"
  timeout 20 $RAC 127.0.0.1:1545 infobase update --cluster=$C --infobase=$uuid --sessions-deny=yes "${AU[@]}" >/dev/null 2>&1
  for s in $(timeout 15 $RAC 127.0.0.1:1545 session list --cluster=$C --infobase=$uuid "${AU[@]}" 2>/dev/null | grep -E '^session ' | awk '{print $3}'); do
    timeout 10 $RAC 127.0.0.1:1545 session terminate --cluster=$C --session=$s "${AU[@]}" >/dev/null 2>&1
  done
  sleep 2
  echo "  удаление инфобазы"
  timeout 25 $RAC 127.0.0.1:1545 infobase drop --cluster=$C --infobase=$uuid "${AU[@]}" 2>&1 | tail -1 | sed 's/^/    /'
  sleep 3
  local PW=$(openssl rand -hex 12)
  $PSQL "psql -c \"alter role $role password '$PW'\"" >/dev/null 2>&1 && echo "  роль $role: новый пароль"
  $PSQL "psql -d $dbase -c \"REASSIGN OWNED BY postgres TO $role\"" >/dev/null 2>&1
  $PSQL "psql -d $dbase -c \"GRANT ALL ON SCHEMA public TO $role\"" >/dev/null 2>&1
  $PSQL "psql -c \"alter database $dbase owner to $role\"" >/dev/null 2>&1
  echo "  создание инфобазы $name"
  timeout 25 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name="$name" \
    --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$dbase" --db-user="$role" \
    --db-pwd="$PW" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -2 | sed 's/^/    /'
  sleep 2
  echo "  страница: $(curl -s --max-time 30 http://127.0.0.1:8081/WEB/$name/ | wc -c) байт"
}

fix_ib goncharov goncharov usr_goncharov 9f9511f4-54b5-46b4-a9b0-40947572f990
fix_ib montesbuh montesbuh usr_montesbuh 92e0ca0d-7464-4026-8258-31f0b87558f5

echo "=== итог: инфобазы ==="
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
