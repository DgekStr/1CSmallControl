#!/bin/bash
echo "=== VM 100: завершён? ==="
ls -la /www/backup/dump/vzdump-qemu-100-* 2>/dev/null | tail -3 | awk '{printf "  %7.0f МБ  %s\n", $5/1048576, $9}'
pgrep -af 'vzdump:100' >/dev/null && echo "  процесс ещё идёт" || echo "  процесс завершён"
tail -4 /var/log/vzdump/qemu-100.log 2>/dev/null | cut -c1-130 | sed 's/^/  /'
echo "=== портал ==="
echo "  healthz: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz 2>/dev/null)"
echo "  версия: $(curl -s http://127.0.0.1:8080/login 2>/dev/null | grep -o 'v2\.0\.[0-9]*' | head -1)"
python3 - <<'PY'
import json
try:
    d = json.load(open('/etc/1c-portal/backup-status.json', encoding='utf-8'))
    print('  бэкап 1С:', d.get('finished_at'), '| ok', d.get('ok'), '| fail', d.get('failed'))
except Exception as e:
    print('  бэкап 1С: нет данных')
PY
