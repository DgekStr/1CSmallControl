#!/bin/bash
echo "=== таймеры и службы архивации ==="
for u in 1c-backup.timer 1c-backup.service 1c-archiv.timer 1c-archiv.service 1c-dump.timer 1c-dump.service; do
  s=$(systemctl list-unit-files "$u" --no-legend 2>/dev/null)
  [ -n "$s" ] && echo "  $s"
done
echo
echo "=== systemd timers (все) ==="
systemctl list-timers --all --no-pager 2>/dev/null | head -12 | sed 's/^/  /'
echo
echo "=== cron ==="
crontab -l 2>/dev/null | grep -i -E 'backup|dump|1c' | sed 's/^/  root: /'
for f in /etc/cron.d/* /etc/cron.daily/*; do
  [ -f "$f" ] && grep -l -i -E 'backup|pg_dump|1cbackup' "$f" 2>/dev/null | while read -r x; do echo "  файл: $x"; done
done
echo
echo "=== статус последнего запуска ==="
[ -f /etc/1c-portal/backup-status.json ] && python3 -c "
import json
d = json.load(open('/etc/1c-portal/backup-status.json', encoding='utf-8'))
for k in ('started_at','finished_at','ok','failed','total','mode','error'):
    if k in d: print('  %-12s %s' % (k, d[k]))
"
echo
echo "=== файлы архивов ==="
ls -la /mnt/1cbackup 2>/dev/null | tail -12 | sed 's/^/  /'
echo "  всего файлов: $(ls /mnt/1cbackup 2>/dev/null | wc -l)"
echo "  точка монтирования: $(mountpoint -q /mnt/1cbackup && echo 'смонтирована' || echo 'НЕ СМОНТИРОВАНА')"
echo
echo "=== юниты архивации ==="
systemctl list-unit-files --no-legend 2>/dev/null | grep -i -E 'backup|archiv|dump' | sed 's/^/  /'
