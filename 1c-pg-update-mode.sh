#!/bin/bash
# Режим обновления 1С: ускоряет реструктуризацию базы за счёт ослабления
# синхронной записи PostgreSQL. Включение обратимо: настройки возвращаются
# к значениям из postgresql.conf командой off.
# Использование: 1c-pg-update-mode on|off|status [имя_базы]
set -uo pipefail

STATE=/etc/1c-portal/pg-update-mode.json
MARK=/etc/1c-portal/pg-mode.state
KEYS="synchronous_commit fsync full_page_writes autovacuum maintenance_work_mem max_wal_size checkpoint_timeout"
DB="${2:-dgek}"

PG() { su -s /bin/bash postgres -c "psql -d postgres -Atc \"$1\"" 2>/dev/null; }
PGD() { su -s /bin/bash postgres -c "psql -d $DB -Atc \"$1\"" 2>/dev/null; }

current_json() {
  python3 - <<'PY'
import json
import subprocess

keys = ("synchronous_commit", "fsync", "full_page_writes", "autovacuum",
        "maintenance_work_mem", "max_wal_size", "checkpoint_timeout")
sql = ("select name || '|' || setting || '|' || source from pg_settings where name in (%s)"
       % ",".join("'%s'" % k for k in keys))
out = subprocess.run(["su", "-s", "/bin/bash", "postgres", "-c",
                      "psql -d postgres -Atc \"%s\"" % sql],
                     capture_output=True, text=True).stdout
data = {}
for line in out.splitlines():
    parts = line.split("|")
    if len(parts) == 3:
        data[parts[0]] = {"value": parts[1], "source": parts[2]}
print(json.dumps(data, indent=1))
PY
}

apply_on() {
  PG "ALTER SYSTEM SET synchronous_commit TO 'off'" >/dev/null
  PG "ALTER SYSTEM SET fsync TO 'off'" >/dev/null
  PG "ALTER SYSTEM SET full_page_writes TO 'off'" >/dev/null
  PG "ALTER SYSTEM SET autovacuum TO 'off'" >/dev/null
  PG "ALTER SYSTEM SET maintenance_work_mem TO '2GB'" >/dev/null
  PG "ALTER SYSTEM SET max_wal_size TO '8GB'" >/dev/null
  PG "ALTER SYSTEM SET checkpoint_timeout TO '30min'" >/dev/null
  PG "SELECT pg_reload_conf()" >/dev/null

  sleep 2
  SSC=$(PG 'show synchronous_commit')
  FS=$(PG 'show fsync')
  if [ "$SSC" = "off" ] && [ "$FS" = "off" ]; then
    echo "on" > "$MARK"; chmod 644 "$MARK"
  echo "режим обновления включён: synchronous_commit=$SSC, fsync=$FS, autovacuum=$(PG 'show autovacuum')"
  else
    echo "ОШИБКА: настройки не применились (synchronous_commit=$SSC, fsync=$FS)"
    exit 3
  fi
  mkdir -p /etc/1c-portal
  current_json > "$STATE"
  chmod 600 "$STATE"
}

apply_off() {
  for key in $KEYS; do
    PG "ALTER SYSTEM RESET $key" >/dev/null
  done
  PG "SELECT pg_reload_conf()" >/dev/null
  sleep 2
  rm -f "$STATE"
  echo "off" > "$MARK"; chmod 644 "$MARK"
  echo "настройки возвращены: synchronous_commit=$(PG 'show synchronous_commit'), fsync=$(PG 'show fsync'), autovacuum=$(PG 'show autovacuum')"

  echo "проверка базы $DB:"
  echo "  таблиц: $(PGD "select count(*) from information_schema.tables where table_schema='public'")"

  su -s /bin/bash postgres -c "psql -d $DB -Atc 'CREATE EXTENSION IF NOT EXISTS amcheck'" >/dev/null 2>&1
  if su -s /bin/bash postgres -c "psql -d $DB -Atc \"select 1 from pg_extension where extname='amcheck'\"" 2>/dev/null | grep -q 1; then
    if su -s /bin/bash postgres -c "pg_amcheck -d $DB --no-dependent-indexes" >/tmp/amcheck.out 2>&1; then
      echo "  проверка целостности: повреждений не найдено"
    else
      echo "  проверка целостности: есть замечания —"
      head -3 /tmp/amcheck.out | sed 's/^/    /'
    fi
  else
    echo "  проверка целостности: расширение amcheck недоступно, пропущено"
  fi
}

case "${1:-status}" in
  on)     apply_on ;;
  off)    apply_off ;;
  status)
    if [ -f "$STATE" ]; then
      echo "on synchronous_commit=$(PG 'show synchronous_commit') fsync=$(PG 'show fsync')"
    else
      echo "off synchronous_commit=$(PG 'show synchronous_commit') fsync=$(PG 'show fsync')"
    fi
    ;;
  *) echo "usage: 1c-pg-update-mode on|off|status [база]"; exit 64 ;;
esac
