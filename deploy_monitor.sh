#!/bin/bash
# Установка мониторинга портала 1С: скрипт, systemd-таймер, sudoers, настройки по умолчанию.
# Запуск: sudo bash deploy_monitor.sh
set -uo pipefail

echo "=== 1. скрипт мониторинга ==="
install -o root -g root -m 755 /tmp/1c-monitor.sh /usr/local/bin/1c-monitor
sed -i '1s/^\xEF\xBB\xBF//' /usr/local/bin/1c-monitor
head -1 /usr/local/bin/1c-monitor

echo
echo "=== 2. systemd: сервис и таймер каждые 10 минут ==="
install -o root -g root -m 644 /tmp/1c-monitor.service /etc/systemd/system/1c-monitor.service
install -o root -g root -m 644 /tmp/1c-monitor.timer /etc/systemd/system/1c-monitor.timer
systemctl daemon-reload
systemctl enable --now 1c-monitor.timer >/dev/null 2>&1
systemctl list-timers 1c-monitor.timer --no-pager 2>/dev/null | head -3 | sed 's/^/  /'

echo
echo "=== 3. права порталу на запуск проверки ==="
if ! grep -q '1c-monitor' /etc/sudoers.d/1c-portal 2>/dev/null; then
  echo 'www-data ALL=(root) NOPASSWD: /usr/local/bin/1c-monitor' >> /etc/sudoers.d/1c-portal
fi
chmod 440 /etc/sudoers.d/1c-portal
grep -c '1c-monitor' /etc/sudoers.d/1c-portal | sed 's/^/  правил: /'

echo
echo "=== 4. настройки по умолчанию ==="
python3 - <<'PY'
import io, json
p = '/etc/1c-portal/settings.json'
d = json.load(io.open(p, encoding='utf-8'))
defaults = {
    'monitor_enabled': '1',
    'monitor_url': 'https://1c.dgek.ru/healthz',
    'monitor_threshold': '2',
    'monitor_disk_min_gb': '10',
    'monitor_backup_max_h': '28',
}
added = 0
for k, v in defaults.items():
    if not d.get(k):
        d[k] = v
        added += 1
io.open(p, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
print('  добавлено настроек:', added)
for k in sorted(defaults):
    print('   %-20s %s' % (k, d[k]))
PY
chown root:www-data /etc/1c-portal/settings.json
chmod 660 /etc/1c-portal/settings.json

echo
echo "=== 5. первый прогон ==="
/usr/local/bin/1c-monitor check
tail -5 /var/log/1c-monitor.log | sed 's/^/  /'
echo
echo "статус:"
python3 - <<'PY'
import json
d = json.load(open('/etc/1c-portal/monitor-status.json'))
print('  ok:', d['ok'], '| время:', d['ts'])
for c in d['checks']:
    print('   %-28s %-5s %s' % (c['title'], 'ok' if c['ok'] else 'FAIL', c['detail']))
PY
