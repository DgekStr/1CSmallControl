#!/bin/bash
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470
AU=(--cluster-user=dgek --cluster-pwd=<CLUSTER_PASSWORD>)
PSQL="su -s /bin/bash postgres -c"

reg() {
  local name=$1 dbase=$2 role=$3
  local pw=$(openssl rand -hex 12)
  $PSQL "psql -c \"alter role $role password '$pw'\"" >/dev/null 2>&1 && echo "  роль $role: пароль обновлён"
  OUT=$(timeout 20 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name="$name" \
        --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$dbase" \
        --db-user="$role" --db-pwd="$pw" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -2)
  echo "  $name → $dbase : ${OUT:-создана}"
}

echo "=== регистрация инфобаз ==="
reg dgek_db dgekdb usr_dgekdb
reg goncharov goncharov usr_goncharov
reg montesbuh montesbuh usr_montesbuh
reg test test usr_test

echo "=== список в кластере ==="
timeout 15 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo

echo "=== настройки портала ==="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/opt/1c-portal/portal.db', timeout=20)
def setv(k, v):
    if c.execute("select 1 from settings where name=?", (k,)).fetchone():
        c.execute("update settings set value=? where name=?", (v, k))
    else:
        c.execute("insert into settings(name, value) values(?,?)", (k, v))
setv('cluster_uuid', 'c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470')
setv('cluster_user', 'dgek')
setv('cluster_pwd', '<CLUSTER_PASSWORD>')
c.commit()
print('  cluster_uuid/user/pwd обновлены')
PY
chown www-data:www-data /opt/1c-portal/portal.db
systemctl restart 1c-portal; sleep 5
echo "  портал: $(systemctl is-active 1c-portal)"

echo "=== проверка ==="
echo "  dgek-db: $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8081/WEB/dgek-db/)"
python3 - <<'PY'
import sys, time; sys.path.insert(0,'/opt/1c-portal')
import os; os.environ.setdefault('PORTAL_DB','/opt/1c-portal/portal.db')
from app import app
app.config['TESTING']=True
with app.test_client() as c:
    with c.session_transaction() as s: s.update(uid=1,user='admin',role='admin',name='A',csrf='t')
    for url in ('/admin/cluster', '/admin/stats', '/admin?tab=bases'):
        t=time.time(); r=c.get(url); print('  %-18s %s %.1f сек' % (url, r.status_code, time.time()-t))
PY
chown www-data:www-data /opt/1c-portal/portal.db
