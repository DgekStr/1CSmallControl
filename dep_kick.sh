#!/bin/bash
set -uo pipefail
cd /tmp
for f in app.py portal.html 1c-kick-user.sh; do sed -i 's/\r$//' "$f"; sed -i '1s/^\xEF\xBB\xBF//' "$f"; done
install -o root -g root -m 755 1c-kick-user.sh /usr/local/bin/1c-kick-user
bash -n /usr/local/bin/1c-kick-user && echo "  скрипт: ok"
grep -q '1c-kick-user' /etc/sudoers.d/1c-portal || echo "www-data ALL=(root) NOPASSWD: /usr/local/bin/1c-kick-user" >> /etc/sudoers.d/1c-portal
chmod 440 /etc/sudoers.d/1c-portal
visudo -c -f /etc/sudoers.d/1c-portal >/dev/null 2>&1 && echo "  sudoers: ok"
install -o root -g www-data -m 640 app.py /opt/1c-portal/app.py
install -o root -g www-data -m 640 portal.html /opt/1c-portal/templates/portal.html
chown www-data:www-data /opt/1c-portal/portal.db
systemctl restart 1c-portal; sleep 5
echo "  портал: $(systemctl is-active 1c-portal), healthz: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz)"
echo "  версия: $(curl -s http://127.0.0.1:8080/login | grep -o 'v2\.0\.[0-9]*' | head -1)"
/usr/local/bin/1c-kick-user dgek 2>&1 | tail -1 | sed 's/^/  тест kick-user: /'
