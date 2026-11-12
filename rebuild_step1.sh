#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
D=/home/usr1cv8/.1cv8/1C/1cv8
BK=/root/reg1541-backup-$(date +%Y%m%d-%H%M).tar.gz

echo "=== 1. бэкап реестра кластера ==="
tar -C "$D" -czf "$BK" reg_1541 2>/dev/null && echo "  локально: $BK ($(du -h "$BK" | cut -f1))"
if [ -d /mnt/1cbackup ] && mountpoint -q /mnt/1cbackup; then
  cp "$BK" /mnt/1cbackup/ && echo "  на NAS: /mnt/1cbackup/$(basename "$BK")"
else
  echo "  NAS /mnt/1cbackup не смонтирован — копирую после монтирования"
fi

echo "=== 2. остановка 1С ==="
systemctl stop ras.service srv1cv8.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null
sleep 3
echo "  процессов: $(pgrep -c -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null || echo 0)"

echo "=== 3. отодвигаю реестр ==="
mv "$D/reg_1541" "$D/reg_1541.bak.$(date +%Y%m%d-%H%M)" && echo "  переименован"
mkdir -p "$D/reg_1541"
chown usr1cv8:grp1cv8 "$D/reg_1541"
chmod 750 "$D/reg_1541"

echo "=== 4. запуск ragent (новый кластер) ==="
systemctl start srv1cv8
for i in $(seq 1 25); do [ "$(systemctl is-active srv1cv8)" = "active" ] && break; sleep 2; done
echo "  srv1cv8: $(systemctl is-active srv1cv8)"
for i in $(seq 1 20); do
  [ "$(ss -ltn | grep -c 1541)" -gt 0 ] && break
  sleep 3
done
echo "  порт 1541: $(ss -ltn | grep -c 1541) | 1540: $(ss -ltn | grep -c 1540)"
echo "  ragent: $(pgrep -c ragent)"
echo "  новый реестр: $(ls "$D/reg_1541" 2>/dev/null | tr '\n' ' ')"

echo "=== 5. запуск ras ==="
systemctl reset-failed ras.service >/dev/null 2>&1
systemctl start ras.service
sleep 10
echo "  ras: $(systemctl is-active ras.service)"

echo "=== 6. новый кластер ==="
T0=$(date +%s%N)
timeout 20 $RAC 127.0.0.1:1545 cluster list 2>&1 | head -10 | sed 's/^/  /'
echo "  время: $(( ($(date +%s%N)-T0)/1000000 )) мс"
