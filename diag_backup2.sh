#!/bin/bash
echo "=== /etc/cron.d/1c-portal-backup ==="
cat /etc/cron.d/1c-portal-backup 2>/dev/null | sed 's/^/  /'
echo "  права: $(stat -c '%a %U:%G' /etc/cron.d/1c-portal-backup 2>/dev/null)"
echo
echo "=== 1c-backup-tick.timer ==="
systemctl cat 1c-backup-tick.timer 2>/dev/null | sed 's/^/  /'
echo
echo "=== 1c-backup-tick.service ==="
systemctl cat 1c-backup-tick.service 2>/dev/null | sed 's/^/  /'
echo
echo "=== статус таймера ==="
systemctl status 1c-backup-tick.timer --no-pager 2>/dev/null | head -8 | sed 's/^/  /'
echo
echo "=== журнал таймера за сутки ==="
journalctl -u 1c-backup-tick.service --since 'yesterday' --no-pager 2>/dev/null | tail -15 | sed 's/^/  /'
echo
echo "=== журнал cron за 04:00 ==="
journalctl -u cron --since '2026-11-08 03:55' --until '2026-11-08 04:20' --no-pager 2>/dev/null | tail -10 | sed 's/^/  /'
grep -i -E '1c-portal-backup|backup' /var/log/syslog 2>/dev/null | tail -5 | sed 's/^/  syslog: /'
echo
echo "=== настройки архивации в БД ==="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/opt/1c-portal/portal.db')
for n, v in c.execute("select name, value from settings where name like 'backup%' order by name"):
    print('  %-24s %r' % (n, v))
PY
