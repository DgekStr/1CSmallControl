#!/bin/bash
set -uo pipefail
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=$IC_CLUSTER
AU=(--cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD)
D=/home/usr1cv8/.1cv8/1C/1cv8
PSQL="su -s /bin/bash postgres -c"
BK=/root/reg1541-surgery-$(date +%Y%m%d-%H%M).tar.gz

echo "=== 1. бэкап реестра ==="
tar -C "$D" -czf "$BK" reg_1541 2>/dev/null && echo "  локально: $BK ($(du -h $BK | cut -f1))"
[ -d /mnt/1cbackup ] && cp "$BK" /mnt/1cbackup/ 2>/dev/null && echo "  на NAS: копия"

echo "=== 2. остановка 1С ==="
systemctl stop ras.service srv1cv8.service 2>/dev/null
pkill -9 -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null
sleep 4
echo "  процессов: $(pgrep -c -f 'ragent|rmngr|rphost|ras cluster' 2>/dev/null || echo 0)"

echo "=== 3. удаляю записи инфобаз из реестра ==="
python3 - <<'PY'
import io, re, sys
D = '/home/usr1cv8/.1cv8/1C/1cv8/reg_1541/'
KILL = {'ab55c2fb-fb28-4b86-8c29-600696ad502d',
        'd27e6313-36da-49f3-a10f-bbd3081ecb4d',
        '24f21c24-f506-44db-ac54-c5182b43d81d'}

def remove_blocks(text, uuids):
    out, i, removed = [], 0, 0
    while i < len(text):
        m = re.match(r'\{(' + '|'.join(re.escape(u) for u in uuids) + r')', text[i:])
        if m:
            # найти парную закрывающую скобку
            depth, j = 0, i
            while j < len(text):
                ch = text[j]
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            j += 1
            # съесть запятую/перевод строки после блока
            while j < len(text) and text[j] in ', \n\r':
                j += 1
            removed += 1
            out.append('')
            i = j
            continue
        out.append(text[i]); i += 1
    return ''.join(out), removed

for fn in ('1CV8Clsto.lst', '1CV8Clst.lst'):
    p = D + fn
    try:
        s = io.open(p, encoding='utf-8', errors='surrogateescape').read()
    except Exception as e:
        print('  ', fn, 'ошибка чтения:', e); continue
    new, n = remove_blocks(s, KILL)
    bal = new.count('{') - new.count('}')
    print('  %s: удалено блоков %d, баланс скобок %d' % (fn, n, bal))
    if bal != 0:
        print('  ОТМЕНА: скобки не сбалансированы, файл не изменён')
        continue
    io.open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='\n').write(new)
PY

echo "=== 4. запуск 1С ==="
systemctl start srv1cv8
for i in $(seq 1 25); do [ "$(systemctl is-active srv1cv8)" = "active" ] && break; sleep 2; done
sleep 30
systemctl start ras.service 2>/dev/null
sleep 10
echo "  srv1cv8: $(systemctl is-active srv1cv8) | ras: $(systemctl is-active ras.service)"
echo "  1541: $(ss -ltn | grep -c 1541)"
echo "=== 5. инфобазы после правки ==="
timeout 20 $RAC 127.0.0.1:1545 infobase summary list --cluster=$C "${AU[@]}" 2>&1 | awk -F' *: *' '/^infobase/{u=$2} /^name/{print "  " u " " $2}'
