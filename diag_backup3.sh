#!/bin/bash
echo "=== файлы /usr/local/bin/1c-* ==="
ls -la /usr/local/bin/1c-* 2>/dev/null | sed 's/^/  /' || echo "  НЕТ НИ ОДНОГО"
echo
echo "=== что ждёт таймер ==="
grep -h ExecStart /etc/systemd/system/1c-backup-tick.service /etc/systemd/system/1c-backup.service 2>/dev/null | sed 's/^/  /'
echo
echo "=== есть ли скрипт в других местах ==="
for p in /opt/1c-portal/1c-backup.sh /root/1c-backup.sh /opt/1c-portal-backup/1c-backup.sh; do
  [ -f "$p" ] && echo "  найден: $p"
done
echo
echo "=== юниты архивации в системе ==="
ls -la /etc/systemd/system/1c-* 2>/dev/null | sed 's/^/  /'
echo
echo "=== cron.d ==="
cat /etc/cron.d/1c-portal-backup 2>/dev/null | sed 's/^/  /'
echo
echo "=== в репозитории проекта ==="
git -C /opt/1c-portal log --oneline -1 2>/dev/null | sed 's/^/  /'
ls /opt/1c-portal/*.sh 2>/dev/null | sed 's/^/  /'
