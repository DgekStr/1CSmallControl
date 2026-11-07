#!/bin/bash
# РЈСЃС‚Р°РЅРѕРІРєР° СЃРёСЃС‚РµРјС‹ Р±СЌРєР°РїРѕРІ 1РЎ: СЃРєСЂРёРїС‚С‹, systemd-С‚Р°Р№РјРµСЂ, sudoers.
set -e

install -m 755 /tmp/1c-backup.sh /usr/local/bin/1c-backup
install -m 755 /tmp/1c-backup-info.sh /usr/local/bin/1c-backup-info
install -m 644 /tmp/1c-backup-tick.service /etc/systemd/system/1c-backup-tick.service
install -m 644 /tmp/1c-backup-tick.timer /etc/systemd/system/1c-backup-tick.timer

# СЃС‚Р°СЂС‹Р№ cron Р±РѕР»СЊС€Рµ РЅРµ РЅСѓР¶РµРЅ вЂ” СЂР°СЃРїРёСЃР°РЅРёРµРј СѓРїСЂР°РІР»СЏРµС‚ РїРѕСЂС‚Р°Р»
rm -f /etc/cron.d/1c-db-backup

DEBIAN_FRONTEND=noninteractive apt-get -y install cifs-utils >/dev/null 2>&1 || true

if ! grep -q '1c-backup' /etc/sudoers.d/1c-settings 2>/dev/null; then
  {
    echo 'www-data ALL=(root) NOPASSWD: /usr/local/bin/1c-backup'
    echo 'www-data ALL=(root) NOPASSWD: /usr/local/bin/1c-backup-info'
    echo 'www-data ALL=(root) NOPASSWD: /usr/local/bin/mount'
    echo 'www-data ALL=(root) NOPASSWD: /usr/bin/mount'
  } >> /etc/sudoers.d/1c-settings
  chmod 440 /etc/sudoers.d/1c-settings
fi
visudo -c >/dev/null && echo "sudoers ok"

systemctl daemon-reload
systemctl enable --now 1c-backup-tick.timer >/dev/null 2>&1
systemctl is-active 1c-backup-tick.timer | sed 's/^/С‚Р°Р№РјРµСЂ: /'

echo
echo "=== С‚РµРєСѓС‰РёРµ РЅР°СЃС‚СЂРѕР№РєРё Р±СЌРєР°РїР° ==="
python3 - <<'PY'
import json
try:
    d = json.load(open('/etc/1c-portal/settings.json', encoding='utf-8'))
except Exception:
    d = {}
for k in ('backup_enabled', 'backup_time', 'backup_keep', 'backup_dir', 'backup_user'):
    print('  %-16s %s' % (k, d.get(k, 'вЂ”')))
PY
