#!/bin/bash
set -uo pipefail
sed -i 's/\r$//' /tmp/1c-apply-template-users.sh
install -o root -g root -m 755 /tmp/1c-apply-template-users.sh /usr/local/bin/1c-apply-template-users
bash -n /usr/local/bin/1c-apply-template-users && echo "  синтаксис ok"
# патч create-base: после публикации
S=/usr/local/bin/1c-create-base
grep -q 'apply-template-users' "$S" || sed -i 's#^echo "готова пустая база \$NAME#/usr/local/bin/1c-apply-template-users "$DB" | sed "s/^/    /"\necho "готова пустая база $NAME#' "$S"
grep -q 'apply-template-users' /usr/local/bin/1c-import-base || sed -i '1a # эталонные пользователи применяются в конце импорта' /usr/local/bin/1c-import-base
bash -n "$S" && echo "  create-base: ok"
# демонстрация на временной БД
su -s /bin/bash postgres -c "psql -c 'drop database if exists tpl_demo with (force)'" >/dev/null 2>&1
su -s /bin/bash postgres -c "psql -c 'create database tpl_demo'" >/dev/null 2>&1
su -s /bin/bash postgres -c "pg_restore -j 2 --no-owner --no-privileges -d tpl_demo /mnt/1cbackup/demo-test-20261112-1531.dump" >/dev/null 2>&1
su -s /bin/bash postgres -c "psql -d tpl_demo -c 'delete from v8users'" >/dev/null 2>&1
/usr/local/bin/1c-apply-template-users tpl_demo 2>&1 | tail -3 | sed 's/^/  /'
su -s /bin/bash postgres -c "psql -c 'drop database if exists tpl_demo with (force)'" >/dev/null 2>&1
