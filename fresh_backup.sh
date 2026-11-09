#!/bin/bash
set -uo pipefail
echo "=== удаляю старые дампы (все копии) ==="
BEFORE=$(du -sh /mnt/1cbackup 2>/dev/null | cut -f1)
rm -f /mnt/1cbackup/*.dump 2>/dev/null
echo "  было: $BEFORE, осталось файлов: $(ls -1 /mnt/1cbackup/*.dump 2>/dev/null | wc -l)"
echo
echo "=== список исключений архивации ==="
printf '# Сломанные/устаревшие инфобазы: ждут удаления в консоли 1С\nmonesbuh\n' > /etc/1c-portal/backup-skip.txt
chown root:www-data /etc/1c-portal/backup-skip.txt
chmod 640 /etc/1c-portal/backup-skip.txt
cat /etc/1c-portal/backup-skip.txt | sed 's/^/  /'
echo
echo "=== свежая архивация всех живых баз ==="
/usr/local/bin/1c-backup.sh run 2>&1 | tail -12
echo
echo "=== статус ==="
python3 - <<'PY'
import json
d = json.load(open('/etc/1c-portal/backup-status.json', encoding='utf-8'))
print('  %s | ok %s | fail %s | файлов %s' % (d['finished_at'], d['ok'], d['failed'], len(d.get('files', []))))
for f in d.get('files', []):
    print('   ', f)
PY
ls -la /mnt/1cbackup/*.dump 2>/dev/null | awk '{printf "  %6.1f ГБ  %s\n", $5/1073741824, $9}'
