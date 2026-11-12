#!/bin/bash
set -uo pipefail
echo "=== чищу зависшие записи заданий (29-34) ==="
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('/opt/1c-portal/portal.db',timeout=20)
rows=list(c.execute("select id,slug,status from jobs where status in ('running','queued') or (status='done' and finished_at is not null and id>=29)"))
print('  к удалению:', rows[-6:])
c.execute("delete from jobs where id between 29 and 34")
c.commit()
print('  осталось заданий:', c.execute('select count(*) from jobs').fetchone()[0])
PY
chown www-data:www-data /opt/1c-portal/portal.db
systemctl restart 1c-portal; sleep 5
echo "  портал: $(systemctl is-active 1c-portal)"
echo "=== запускаю архивацию через портал (как кнопка) ==="
python3 - <<'PY'
import sys, time; sys.path.insert(0,'/opt/1c-portal')
import os; os.environ.setdefault('PORTAL_DB','/opt/1c-portal/portal.db')
from app import app, _job_start, _job_band
app.config['TESTING']=True
with app.app_context():
    jid, job = _job_start('backup', 'Архивация баз 1С', ['/usr/local/bin/1c-backup.sh', 'run'], 1)
    print('  задание:', jid)
    for i in range(60):
        time.sleep(3)
        from app import db
        r = db().execute("select status, finished_at from jobs where slug=?", (jid,)).fetchone()
        if r and r['status'] in ('done','failed'):
            print('  статус:', r['status'], '| финиш:', r['finished_at'], '| ждал', i*3, 'сек')
            break
PY
chown www-data:www-data /opt/1c-portal/portal.db
echo "=== статус бэкапа ==="
python3 -c "
import json; d=json.load(open('/etc/1c-portal/backup-status.json')); print('  ', d.get('finished_at'), 'ok', d.get('ok'), 'fail', d.get('failed'), '| файлов:', len(d.get('files') or []))" 2>/dev/null
