#!/bin/bash
set -uo pipefail
echo "=== 1. резервная копия текущих бинарников 2342 ==="
tar -C /opt/1cv8/x86_64 -czf /root/1cv8-2342-backup-$(date +%Y%m%d-%H%M).tar.gz 8.3.27.2342 2>/dev/null && echo "  бекап: $(ls -lh /root/1cv8-2342-backup-*.tar.gz | tail -1 | awk '{print $9, $5}')"
echo "=== 2. остановка служб ==="
systemctl stop ras.service srv1cv8.service 2>/dev/null
sleep 3
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null
sleep 2
echo "  процессов 1С: $(pgrep -c -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null || echo 0)"
echo "=== 3. установка пакетов 2342 ==="
DEBIAN_FRONTEND=noninteractive dpkg -i /tmp/1c-deb/*.deb 2>&1 | grep -E 'Setting up|Unpacking|error|Ошибка' | tail -14 | sed 's/^/  /'
echo "  версия ras: $(/opt/1cv8/x86_64/8.3.27.2342/ras --version 2>&1 | head -1)"
echo "=== 4. запуск srv1cv8 ==="
systemctl start srv1cv8
for i in $(seq 1 20); do [ "$(systemctl is-active srv1cv8)" = "active" ] && break; sleep 2; done
echo "  srv1cv8: $(systemctl is-active srv1cv8)"
sleep 25
echo "=== 5. запуск ras ==="
systemctl reset-failed ras.service >/dev/null 2>&1
systemctl start ras.service
sleep 10
echo "  ras: $(systemctl is-active ras.service)"
echo "=== 6. тест rac (15 с) ==="
T0=$(date +%s%N)
timeout 15 /opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 cluster list 2>&1 | head -6 | sed 's/^/  /'
echo "  время: $(( ($(date +%s%N)-T0)/1000000 )) мс"
echo "=== 7. сеансы и базы ==="
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
timeout 10 /opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 infobase summary list --cluster=$IC_CLUSTER --cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
