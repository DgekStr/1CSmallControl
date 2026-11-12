#!/bin/bash
set -uo pipefail
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=$IC_CLUSTER
AU=(--cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD)
D=/home/usr1cv8/.1cv8/1C/1cv8
PSQL="su -s /bin/bash postgres -c"

systemctl stop ras.service srv1cv8.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null
sleep 3

python3 - <<'PY'
import io, re, sys
D = '/home/usr1cv8/.1cv8/1C/1cv8/reg_1541/'
KILL = {'ab55c2fb-fb28-4b86-8c29-600696ad502d',
        'd27e6313-36da-49f3-a10f-bbd3081ecb4d',
        '24f21c24-f506-44db-ac54-c5182b43d81d'}
ok = True
for fn in ('1CV8Clsto.lst', '1CV8Clst.lst'):
    p = D + fn
    s = io.open(p, encoding='utf-8', errors='surrogateescape').read()
    removed = 0
    for u in KILL:
        idx = s.find('{' + u)
        if idx < 0:
            continue
        depth, j = 0, idx
        while j < len(s):
            if s[j] == '{': depth += 1
            elif s[j] == '}':
                depth -= 1
                if depth == 0: break
            j += 1
        j += 1
        while j < len(s) and s[j] in ', \n\r':
            j += 1
        s = s[:idx] + s[j:]
        removed += 1
    # уменьшить счётчик списка: ищем "{N," перед первым оставшимся uuid-блоком
    if removed:
        m = re.search(r'\{(\d+),(\s*)\{([0-9a-f]{8}-[0-9a-f]{4}-)', s)
        if m:
            n = int(m.group(1))
            s = s[:m.start(1)] + str(max(0, n - removed)) + s[m.end(1):]
            print('  %s: удалено %d, счётчик %d -> %d' % (fn, removed, n, max(0, n - removed)))
        else:
            print('  %s: счётчик списка не найден' % fn); ok = False
    bal = s.count('{') - s.count('}')
    print('  %s: баланс скобок %d' % (fn, bal))
    if bal != 0:
        ok = False
    if ok:
        io.open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='\n').write(s)
if not ok:
    print('  ОШИБКА разбора — файлы не сохранены')
    sys.exit(1)
PY
if [ $? -ne 0 ]; then
  echo "=== откат: правка не удалась ==="
  BK=$(ls -1t /root/reg1541-surgery-*.tar.gz | head -1)
  rm -rf "$D/reg_1541"; tar -C "$D" -xzf "$BK"
  systemctl start srv1cv8; sleep 30; systemctl start ras.service
  exit 1
fi

systemctl start srv1cv8
sleep 40
systemctl start ras.service 2>/dev/null
sleep 10
echo "=== состояние ==="
echo "  srv1cv8: $(systemctl is-active srv1cv8) | 1541: $(ss -ltn | grep -c 1541) | rmngr: $(pgrep -c rmngr)"
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>&1 | awk -F' *: *' '/^infobase/{u=$2} /^name/{print "  " u " " $2}'

echo "=== создаю dgek_db и goncharov заново ==="
for pair in "dgek_db dgekdb usr_dgekdb" "goncharov goncharov usr_goncharov"; do
  set -- $pair; name=$1; db=$2; role=$3
  PW=$(openssl rand -hex 12)
  $PSQL "psql -c \"alter role $role password '$PW'\"" >/dev/null 2>&1
  $PSQL "psql -d $db -c \"REASSIGN OWNED BY postgres TO $role\"" >/dev/null 2>&1
  $PSQL "psql -d $db -c \"GRANT ALL ON SCHEMA public TO $role\"" >/dev/null 2>&1
  timeout 30 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name="$name" \
    --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$db" --db-user="$role" \
    --db-pwd="$PW" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -1 | sed 's/^/  /'
done
sleep 5
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo
