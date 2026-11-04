#!/bin/bash
# Счётчик клиентских лицензий 1С.
# Всего мест — по ключам HASP (/etc/usbhaspd/keys), занято — по активным сеансам 1С.
# Вывод: «<занято> <всего> <сетевых> <локальных>»
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

export IC_RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
export IC_RAS=${IC_RAS:-127.0.0.1:1545}

python3 - <<'PY'
import glob
import json
import os
import re
import subprocess

rac = os.environ['IC_RAC']
ras = os.environ['IC_RAS']

# --- всего мест по ключам ---
network = local = 0
seen = set()
for path in sorted(glob.glob('/etc/usbhaspd/keys/*.json')):
    try:
        key = json.load(open(path, encoding='utf-8')).get('HASP Key', {})
    except Exception:
        continue
    sn = key.get('SN') or path
    if sn in seen:           # один и тот же ключ в x32/x64
        continue
    seen.add(sn)
    name = key.get('Name') or ''
    match = re.search(r'(\d+)\s*User', name, re.I)
    if match:
        network += int(match.group(1))
    elif name.startswith('ORG'):
        pass
    else:
        local += 1

# --- занято: клиентские сеансы ---
used = 0
try:
    clusters = subprocess.run([rac, ras, 'cluster', 'list'],
                              capture_output=True, text=True, timeout=20).stdout
    uuid = ''
    for line in clusters.splitlines():
        if line.strip().startswith('cluster') and ':' in line:
            uuid = line.split(':', 1)[1].strip()
            break
    if uuid:
        out = subprocess.run([rac, ras, 'session', 'list', '--cluster', uuid],
                             capture_output=True, text=True, timeout=20).stdout
        apps = [l.split(':', 1)[1].strip() for l in out.splitlines() if l.strip().startswith('app-id')]
        used = sum(1 for a in apps if a in ('WebClient', '1CV8', '1CV8C', 'Designer', 'COMConnection'))
except Exception:
    used = 0

print('%d %d %d %d' % (used, network + local, network, local))
PY
