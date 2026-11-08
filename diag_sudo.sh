#!/bin/bash
echo "=== sudoers для портала ==="
ls -la /etc/sudoers.d/ 2>/dev/null | sed 's/^/  /'
for f in /etc/sudoers.d/*1c* /etc/sudoers.d/*portal*; do
  [ -f "$f" ] && { echo "--- $f"; cat "$f" | sed 's/^/  /'; }
done
echo
echo "=== есть ли право на 1c-sandbox ==="
grep -r "1c-sandbox" /etc/sudoers /etc/sudoers.d/ 2>/dev/null | sed 's/^/  /' || echo "  НЕТ"
echo
echo "=== остатки упавшей песочницы ==="
su -s /bin/bash postgres -c "psql -Atc \"select datname from pg_database where datname like 'sb_%' or datname like '%restore%'\"" 2>/dev/null | sed 's/^/  БД: /'
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
/opt/1cv8/x86_64/8.3.27.2342/rac 127.0.0.1:1545 infobase summary list \
  --cluster="${IC_CLUSTER}" --cluster-user="${IC_CLUSTER_USER}" --cluster-pwd="${IC_CLUSTER_PWD}" 2>/dev/null \
  | awk -F' *: *' '/^name/{print "  инфобаза: " $2}' | grep -E 'sb_|restore'
echo
echo "=== публикации ==="
ls /var/www/1c/ 2>/dev/null | grep -E 'sb_|restore' | sed 's/^/  /' || echo "  нет"
