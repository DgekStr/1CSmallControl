#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
echo "=== A1. остановка и очистка ==="
systemctl stop srv1cv8 ras.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null; sleep 3
echo "  процессов: $(pgrep -c -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null || echo 0)"

echo "=== A2. purge пакетов 2342 ==="
DEBIAN_FRONTEND=noninteractive apt-get purge -y '1c-enterprise-8.3.27.2342-*' 2>&1 | grep -E 'Removing|Purging|error' | tail -10 | sed 's/^/  /'
echo "  осталось пакетов 2342: $(dpkg -l 2>/dev/null | grep -c '8.3.27.2342')"

echo "=== A3. чистая установка ==="
rm -rf /opt/1cv8/x86_64/8.3.27.2342 2>/dev/null
DEBIAN_FRONTEND=noninteractive dpkg -i /tmp/1c-deb/*.deb 2>&1 | grep -E 'Setting up|error|dpkg:' | tail -10 | sed 's/^/  /'
echo "  установлено пакетов: $(dpkg -l 2>/dev/null | grep -c '8.3.27.2342')"
echo "  версия: $(/opt/1cv8/x86_64/8.3.27.2342/rac --version 2>&1 | head -1)"

echo "=== A4. пустой реестр ==="
D=/home/usr1cv8/.1cv8/1C/1cv8
rm -rf "$D/reg_1541"
mkdir -p "$D/reg_1541"
chown -R usr1cv8:grp1cv8 "$D"
chmod 750 "$D/reg_1541"
echo "  реестр: $(ls -la $D | grep reg_1541 | awk '{print $1, $3, $4}')"

echo "=== A5. запуск 1С ==="
systemctl daemon-reload 2>/dev/null
systemctl reset-failed srv1cv8 ras.service 2>/dev/null
systemctl start srv1cv8
for i in $(seq 1 25); do [ "$(systemctl is-active srv1cv8)" = "active" ] && break; sleep 2; done
echo "  srv1cv8: $(systemctl is-active srv1cv8)"
for i in $(seq 1 25); do [ "$(ss -ltn | grep -c 1541)" -gt 0 ] && break; sleep 3; done
echo "  1541: $(ss -ltn | grep -c 1541) | 1540: $(ss -ltn | grep -c 1540) | ragent: $(pgrep -c ragent)"

echo "=== A6. ras + тест ==="
systemctl start ras.service
sleep 10
echo "  ras: $(systemctl is-active ras.service)"
T0=$(date +%s%N)
timeout 20 $RAC 127.0.0.1:1545 cluster list 2>&1 | head -12 | sed 's/^/  /'
echo "  время: $(( ($(date +%s%N)-T0)/1000000 )) мс"
