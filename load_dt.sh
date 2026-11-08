#!/bin/bash
echo "=== файл на сервере ==="
ls -l /tmp/podolsky-1Cv8.dt 2>/dev/null || echo "  файла нет"
md5sum /tmp/podolsky-1Cv8.dt 2>/dev/null | cut -d' ' -f1 | sed 's/^/  md5: /'
echo
echo "=== загрузка .dt в базу test ==="
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
IB=$(/opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 infobase summary list \
      --cluster="${IC_CLUSTER}" --cluster-user="${IC_CLUSTER_USER}" --cluster-pwd="${IC_CLUSTER_PWD}" 2>/dev/null \
     | awk '/^infobase/{u=$3} /^name/{if ($3=="test") {print u; exit}}')
echo "  инфобаза test: $IB"
echo "  завершаю сеансы"
/usr/local/bin/1c-kick-sessions test >/dev/null 2>&1 || true
sleep 2
echo "  восстанавливаю из dt (это может занять несколько минут)"
/opt/1cv8/x86_64/8.3.27.2342/1cv8 DESIGNER /S"127.0.0.1/test" /N"Евгений" /P"26082001" \
  /RestoreIB /tmp/podolsky-1Cv8.dt /Out/tmp/restore-dt.log 2>&1 | tail -5
echo "  код: $?"
echo "=== лог ==="
tail -5 /tmp/restore-dt.log 2>/dev/null | sed 's/^/  /'
