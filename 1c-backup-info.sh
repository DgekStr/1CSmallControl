#!/bin/bash
# Backup info for the portal (JSON).
set -uo pipefail

python3 - <<'PY'
import json, os, subprocess

def settings():
    try:
        return json.load(open('/etc/1c-portal/settings.json', encoding='utf-8'))
    except Exception:
        return {}

s = settings()
d = s.get('backup_dir', '/var/lib/1c-backups')
target = d
if d.startswith('//'):
    target = '/mnt/1cbackup'

def human(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return '%.1f %s' % (n, unit)
        n /= 1024.0

free = total = None
try:
    st = os.statvfs(target)
    free = st.f_bavail * st.f_frsize
    total = st.f_blocks * st.f_frsize
except OSError:
    pass

status = {}
try:
    status = json.load(open('/etc/1c-portal/backup-status.json', encoding='utf-8'))
except Exception:
    pass

files = []
try:
    for name in sorted(os.listdir(target))[-10:]:
        p = os.path.join(target, name)
        if os.path.isfile(p):
            files.append({'name': name, 'size': human(os.path.getsize(p))})
except OSError:
    pass

print(json.dumps({
    'enabled': s.get('backup_enabled', '1'),
    'time': s.get('backup_time', '04:00'),
    'keep': s.get('backup_keep', '14'),
    'dir': d,
    'target': target,
    'mounted': os.path.ismount('/mnt/1cbackup'),
    'free': human(free) if free is not None else '-',
    'total': human(total) if total is not None else '-',
    'free_bytes': free or 0,
    'last_run': status.get('finished_at', ''),
    'last_ok': status.get('ok', 0),
    'last_fail': status.get('failed', 0),
    'files': files,
}, ensure_ascii=False))
PY
