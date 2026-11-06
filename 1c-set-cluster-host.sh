#!/bin/bash
# Меняет адрес, который кластер 1С объявляет клиентам (реестр кластера).
# Использование: 1c-set-cluster-host <новый_адрес>
set -uo pipefail

NEW="${1:-}"
[ -n "$NEW" ] || { echo "usage: 1c-set-cluster-host <host>"; exit 64; }

RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
RAS=127.0.0.1:1545
REG=/home/usr1cv8/.1cv8/1C/1cv8/reg_1541
STAMP=$(date +%Y%m%d%H%M%S)

CUR=$($RAC "$RAS" server list --cluster=e3220a07-7374-4fc0-b4fb-25ace3789930 2>/dev/null \
      | awk -F' *: *' '/^agent-host/{print $2; exit}')
CUR=${CUR:-1c.dgek.ru}

if [ "$CUR" = "$NEW" ]; then
  echo "кластер уже объявляет $NEW"
  exit 0
fi

echo "адрес кластера: $CUR -> $NEW"
systemctl stop srv1cv8
sleep 2

BACKUP=/var/backups/1c-cluster-$STAMP.tar.gz
mkdir -p /var/backups
tar -czf "$BACKUP" -C "$REG" 1CV8Clst.lst 1CV8Clsto.lst 2>/dev/null
echo "резервная копия: $BACKUP"

for f in 1CV8Clst.lst 1CV8Clsto.lst; do
  [ -f "$REG/$f" ] || continue
  sed -i "s/$CUR/$NEW/g" "$REG/$f"
  chown usr1cv8:grp1cv8 "$REG/$f"
  chmod 640 "$REG/$f"
done

systemctl start srv1cv8
for _ in $(seq 1 30); do
  systemctl is-active --quiet srv1cv8 && sleep 4 && break
  sleep 2
done

NOW=$($RAC "$RAS" server list --cluster=e3220a07-7374-4fc0-b4fb-25ace3789930 2>/dev/null \
      | awk -F' *: *' '/^agent-host/{print $2; exit}')

if [ "$NOW" = "$NEW" ]; then
  echo "готово: кластер объявляет $NOW"
  $RAC "$RAS" infobase info --cluster=e3220a07-7374-4fc0-b4fb-25ace3789930 --name=dgek \
       --infobase-user=Евгений --infobase-pwd=26082001 2>/dev/null | grep -E 'infobase|descr' | head -2
else
  echo "ОШИБКА: кластер объявляет '$NOW', откатываю"
  systemctl stop srv1cv8
  tar -xzf "$BACKUP" -C "$REG"
  systemctl start srv1cv8
  exit 2
fi
