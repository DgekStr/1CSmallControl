#!/bin/bash
set -uo pipefail
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=$IC_CLUSTER
AU=(--cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD)
D=/home/usr1cv8/.1cv8/1C/1cv8
PSQL="su -s /bin/bash postgres -c"

echo "=== 1. остановка ==="
systemctl stop ras.service srv1cv8.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null; sleep 3

echo "=== 2. архив реестра ==="
tar -C "$D" -czf /root/reg-final-$(date +%H%M).tar.gz reg_1541 2>/dev/null && echo "  ok"

echo "=== 3. очистка списка инфобаз ==="
python3 - <<'PY'
import io, re
D='/home/usr1cv8/.1cv8/1C/1cv8/reg_1541/'
first='ab55c2fb-fb28-4b86-8c29-600696ad502d'
for fn in ('1CV8Clsto.lst','1CV8Clst.lst'):
    p=D+fn
    s=io.open(p,encoding='utf-8',errors='surrogateescape').read()
    idx=s.find('{'+first)
    if idx<0:
        print(' ',fn,'список инфобаз не найден'); continue
    # ищем назад начало блока "{N," 
    j=idx
    start=None
    while j>0:
        j-=1
        if s[j]=='{' and re.match(r'\{\d+,', s[j:j+12]):
            start=j; break
    if start is None:
        print(' ',fn,'счётчик не найден'); continue
    depth=0; k=start
    while k<len(s):
        if s[k]=='{': depth+=1
        elif s[k]=='}':
            depth-=1
            if depth==0: break
        k+=1
    s=s[:start]+'{0}'+s[k+1:]
    bal=s.count('{')-s.count('}')
    print(' ',fn,'список обнулён, баланс',bal)
    if bal==0:
        io.open(p,'w',encoding='utf-8',errors='surrogateescape',newline='\n').write(s)
PY
echo "=== 4. удаление каталогов инфобаз ==="
for u in ab55c2fb-fb28-4b86-8c29-600696ad502d 4311f604-585f-4d87-b366-0909eee9d59e d27e6313-36da-49f3-a10f-bbd3081ecb4d 24f21c24-f506-44db-ac54-c5182b43d81d; do
  rm -rf "$D/reg_1541/$u" && echo "  удалён $u"
done

echo "=== 5. запуск кластера ==="
systemctl start srv1cv8
sleep 40
systemctl start ras.service 2>/dev/null
sleep 10
echo "  1541: $(ss -ltn | grep -c 1541) | rmngr: $(pgrep -c rmngr)"

echo "=== 6. регистрация баз ==="
reg() {
  local name=$1 db=$2 role=$3
  local PW=$(openssl rand -hex 12)
  $PSQL "psql -c \"alter role $role password '$PW'\"" >/dev/null 2>&1
  $PSQL "psql -d $db -c \"REASSIGN OWNED BY postgres TO $role\"" >/dev/null 2>&1
  $PSQL "psql -d $db -c \"GRANT ALL ON SCHEMA public TO $role\"" >/dev/null 2>&1
  timeout 30 $RAC 127.0.0.1:1545 infobase create --cluster=$C --name="$name" \
    --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$db" --db-user="$role" \
    --db-pwd="$PW" --locale=ru_RU --license-distribution=allow "${AU[@]}" 2>&1 | tail -1 | sed 's/^/  /'
}
reg test test usr_test
reg dgek_db dgekdb usr_dgekdb
reg goncharov goncharov usr_goncharov
sleep 4
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>/dev/null | awk -F' *: *' '/^name/{printf "  %s ", $2}'; echo

echo "=== 7. копирую юзера dgek из test в dgekdb и goncharov ==="
$PSQL "psql -d test -c \"\\copy (select * from v8users where name='dgek') to '/tmp/dgek_user.txt'\"" >/dev/null 2>&1
echo "  извлечено: $(wc -l < /tmp/dgek_user.txt 2>/dev/null || echo 0) строк"
for target in dgekdb goncharov; do
  $PSQL "psql -d $target -c \"delete from v8users where name='dgek'\"" >/dev/null 2>&1
  $PSQL "psql -d $target -c \"\\copy v8users from '/tmp/dgek_user.txt'\"" 2>&1 | tail -1 | sed \'s/^/  /\'
done
for target in dgekdb goncharov test; do
  echo "  $target: $(su -s /bin/bash postgres -c "psql -d $target -Atc \\"select count(*) from v8users where name='dgek'\\"" 2>/dev/null) юзер(ов) dgek"
done
echo "=== 8. проверка ==="
for b in test dgek-db goncharov; do echo "  $b: $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8081/WEB/$b/)"; done
