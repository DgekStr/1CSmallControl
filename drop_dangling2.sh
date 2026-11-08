#!/bin/bash
set -uo pipefail
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C="$IC_CLUSTER"
echo "=== удаляю висячую инфобазу sb_test_11081718 (базы PostgreSQL нет) ==="
U=$($RAC 127.0.0.1:1545 infobase summary list --cluster="$C" --cluster-user="$IC_CLUSTER_USER" --cluster-pwd="$IC_CLUSTER_PWD" 2>/dev/null | awk '/^infobase/{u=$3} /^name/{if ($3=="sb_test_11081718"){print u; exit}}')
if [ -n "$U" ]; then
  $RAC 127.0.0.1:1545 infobase drop --cluster="$C" --infobase="$U" --cluster-user="$IC_CLUSTER_USER" --cluster-pwd="$IC_CLUSTER_PWD" 2>&1 | sed 's/^/  /'
  echo "  удалена: $U"
else
  echo "  не найдена"
fi
echo "=== инфобазы после ==="
$RAC 127.0.0.1:1545 infobase summary list --cluster="$C" --cluster-user="$IC_CLUSTER_USER" --cluster-pwd="$IC_CLUSTER_PWD" 2>/dev/null | awk -F' *: *' '/^name/{print "  " $2}'
