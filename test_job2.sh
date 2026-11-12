#!/bin/bash
python3 - <<'PY'
import sys, time, json; sys.path.insert(0,'/opt/1c-portal')
import os; os.environ.setdefault('PORTAL_DB','/opt/1c-portal/portal.db')
from app import app, _job_start, db
app.config['TESTING']=True
with app.app_context():
    jid, job = _job_start('backup', 'Архивация баз 1С', ['/usr/local/bin/1c-backup.sh', 'run'], 1)
    print('  задание:', jid)
    for i in range(80):
        time.sleep(3)
        r = db().execute("select status, finished_at from jobs where slug=?", (jid,)).fetchone()
        if r and r['status'] in ('done','failed'):
            print('  статус:', r['status'], '| ждал', i*3, 'сек')
            break
    else:
        print('  всё ещё выполняется (проверю позже)')
try:
    d = json.load(open('/etc/1c-portal/backup-status.json'))
    print('  бэкап:', d.get('finished_at'), 'ok', d.get('ok'), 'fail', d.get('failed'), 'файлов', len(d.get('files') or []))
except Exception as e:
    print('  статус бэкапа: нет данных')
PY
chown www-data:www-data /opt/1c-portal/portal.db
