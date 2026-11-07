#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Мониторинг портала 1С: доступность, свободное место, актуальность бэкапа.
# Запускается таймером 1c-monitor.timer каждые 10 минут.
#  1c-monitor check    — одна проверка (таймер)
#  1c-monitor status   — JSON для портала
#  1c-monitor test     — прогон без отправки в Mattermost
set -uo pipefail

CONF=/etc/1c-portal/settings.json
STATUS_DIR=/var/lib/1c-monitor
STATUS_FILE=/etc/1c-portal/monitor-status.json
STATE=$STATUS_DIR/state.json
LOG=/var/log/1c-monitor.log

mkdir -p "$STATUS_DIR"
touch "$LOG"

json_get() {
  python3 - "$CONF" "$1" "$2" <<'PY'
import json, sys
path, key, default = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(path, encoding='utf-8'))
except Exception:
    data = {}
value = data.get(key, default)
print(value if value not in (None, '') else default)
PY
}

MODE="${1:-check}"
URL="$(json_get monitor_url 'https://1c.dgek.ru/healthz')"
HOOK="$(json_get monitor_hook '')"
THRESHOLD="$(json_get monitor_threshold '2')"
DISK_MIN="$(json_get monitor_disk_min_gb '10')"
BACKUP_MAX="$(json_get monitor_backup_max_h '28')"
ENABLED="$(json_get monitor_enabled '1')"
RESOLVE="$(json_get monitor_resolve '1c.dgek.ru:443:192.168.0.15')"

python3 - "$MODE" "$URL" "$HOOK" "$THRESHOLD" "$DISK_MIN" "$BACKUP_MAX" "$ENABLED" \
         "$STATUS_FILE" "$STATE" "$LOG" "$RESOLVE" <<'PY'
import json, os, shutil, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

(mode, url, hook, threshold, disk_min, backup_max, enabled,
 status_file, state_file, log_file, resolve) = sys.argv[1:12]

threshold = max(1, int(threshold or 2))
disk_min = float(disk_min or 10)
backup_max = float(backup_max or 28)

def log(text):
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(log_file, 'a', encoding='utf-8') as fh:
            fh.write('[%s] %s\n' % (stamp, text))
    except OSError:
        pass

def load(path, default):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return default

def save(path, data):
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log('не смог записать %s: %s' % (path, exc))

def mm_send(text):
    if not hook:
        return False
    payload = json.dumps({'text': text}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(hook, data=payload,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            log('Mattermost: %s' % ('отправлено' if ok else 'код %s' % resp.status))
            return ok
    except Exception as exc:
        log('Mattermost ошибка: %s' % exc)
        return False

def check_http():
    try:
        cmd = ['curl', '-fsS', '--max-time', '15', '-o', '/dev/null',
               '-w', '%{http_code} %{time_total}']
        if resolve:
            cmd += ['--resolve', resolve]
        cmd.append(url)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        code, _, elapsed = (out.stdout or '').strip().partition(' ')
        if out.returncode == 0 and code.startswith('2'):
            return True, 'HTTP %s за %s с' % (code, round(float(elapsed or 0), 2))
        return False, 'HTTP %s%s' % (code or '—', (' ' + out.stderr.strip()[:80]) if out.stderr else '')
    except Exception as exc:
        return False, 'ошибка проверки: %s' % exc

def check_disk(label, path):
    try:
        total, used, free = shutil.disk_usage(path)
        free_gb = free / 1024 ** 3
        ok = free_gb >= disk_min
        return ok, '%s: %.1f ГБ свободно (порог %.0f ГБ)' % (label, free_gb, disk_min)
    except Exception as exc:
        return False, '%s: не удалось проверить (%s)' % (label, exc)

def check_backup():
    data = load('/etc/1c-portal/backup-status.json', {})
    finished = data.get('finished_at') or ''
    if not finished:
        return False, 'бэкап ещё не запускался'
    try:
        dt = datetime.strptime(finished, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return False, 'непонятная дата бэкапа: %s' % finished
    age_h = (datetime.now() - dt).total_seconds() / 3600
    failed = int(data.get('failed') or 0)
    ok_count = int(data.get('ok') or 0)
    ok = age_h <= backup_max and failed == 0 and ok_count > 0
    if failed:
        return False, 'последний бэкап с ошибками: %s из %s' % (failed, ok_count + failed)
    return ok, 'последний бэкап %s (%.1f ч назад, копий %s)' % (finished, age_h, ok_count)

state = load(state_file, {})
checks = []
if enabled in ('1', 'true', 'yes'):
    checks = [
        ('http', 'Доступность портала', check_http()),
        ('disk_root', 'Место на системном диске', check_disk('корень', '/')),
        ('disk_pg', 'Место на диске PostgreSQL', check_disk('PostgreSQL', '/var/lib/pgpro')),
        ('backup', 'Актуальность бэкапа', check_backup()),
    ]
else:
    log('мониторинг выключен в настройках')

now = time.time()
problems, recovered = [], []

for key, title, (ok, detail) in checks:
    item = state.get(key, {'fails': 0, 'alerted': 0})
    if ok:
        if item.get('fails', 0) >= threshold:
            recovered.append('%s — снова в норме (%s)' % (title, detail))
        item['fails'] = 0
        item['alerted'] = 0
    else:
        item['fails'] = item.get('fails', 0) + 1
        if item['fails'] >= threshold and now - item.get('alerted', 0) > 3600:
            problems.append('%s — %s (подряд %d)' % (title, detail, item['fails']))
            item['alerted'] = now
    item['ok'] = ok
    item['detail'] = detail
    state[key] = item

ok_all = all(c[2][0] for c in checks) if checks else True
status = {
    'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'ok': ok_all,
    'enabled': enabled in ('1', 'true', 'yes'),
    'url': url,
    'checks': [{'key': k, 'title': t, 'ok': d[0], 'detail': d[1],
                'fails': state.get(k, {}).get('fails', 0)} for k, t, d in checks],
}
save(state_file, state)
save(status_file, status)

if mode == 'notify-test':
    text = ('### 🔔 Проверка связи\n\nМониторинг портала 1С: тестовое сообщение. '
            'Если вы его видите — хук настроен верно.')
    ok = mm_send(text)
    print('ok' if ok else 'fail')
    raise SystemExit(0)

if problems:
    text = '### ⚠️ Мониторинг портала 1С\n\n' + '\n'.join('- ' + p for p in problems)
    if mode != 'test':
        mm_send(text)
    log('тревога: ' + '; '.join(problems))
if recovered:
    text = '### ✅ Портал 1С: восстановление\n\n' + '\n'.join('- ' + r for r in recovered)
    if mode != 'test':
        mm_send(text)
    log('восстановление: ' + '; '.join(recovered))
if not problems and not recovered:
    log('проверка: %s' % ('всё в норме' if ok_all else 'есть проблемы ниже порога'))

if mode == 'status':
    print(json.dumps(status, ensure_ascii=False))
PY