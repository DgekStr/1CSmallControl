#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# 1C (PostgreSQL) backup according to portal settings.
# Usage: 1c-backup [run|auto]
set -uo pipefail

STATUS=/etc/1c-portal/backup-status.json
SMB_CRED=/etc/1c-backup/smb.cred
MOUNT=/mnt/1cbackup
LOG=/var/log/1c-backup.log
CLCONF=/etc/1c-portal/1c-session-admin.conf

[ -f "$CLCONF" ] && . "$CLCONF"

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CLUSTER=${IC_CLUSTER:-e3220a07-7374-4fc0-b4fb-25ace3789930}

mkdir -p /var/log "$(dirname "$STATUS")" 2>/dev/null

setting() {
  python3 - "$1" "$2" <<'PY'
import json, sys
try:
    data = json.load(open('/etc/1c-portal/settings.json', encoding='utf-8'))
except Exception:
    data = {}
print(data.get(sys.argv[1], sys.argv[2]))
PY
}

ENABLED=$(setting backup_enabled 1)
TIME=$(setting backup_time 04:00)
KEEP=$(setting backup_keep 14)
DIR=$(setting backup_dir /var/lib/1c-backups)
SMB_USER=$(setting backup_user '')
SMB_PASS=$(setting backup_pass '')
MODE="${1:-run}"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

if [ "$MODE" = "auto" ]; then
  [ "$ENABLED" = "1" ] || exit 0
  [ "$(date +%H:%M)" = "$TIME" ] || exit 0
  LAST=$(python3 - <<'PY'
import json
try:
    d = json.load(open('/etc/1c-portal/backup-status.json', encoding='utf-8'))
    print((d.get('finished_at') or '')[:10])
except Exception:
    print('')
PY
)
  [ "$LAST" = "$(date +%F)" ] && exit 0
fi

TARGET="$DIR"
if [[ "$DIR" == //* ]]; then
  UNC="$DIR"
  command -v mount.cifs >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get -y install cifs-utils >>"$LOG" 2>&1
  mkdir -p /etc/1c-backup "$MOUNT"
  chmod 700 /etc/1c-backup
  printf 'username=%s\npassword=%s\n' "$SMB_USER" "$SMB_PASS" > "$SMB_CRED"
  chmod 600 "$SMB_CRED"
  mountpoint -q "$MOUNT" && umount "$MOUNT" 2>/dev/null
  UID_PG=$(id -u postgres)
  GID_WWW=$(id -g www-data)
  mount -t cifs "$UNC" "$MOUNT" \
    -o "credentials=$SMB_CRED,vers=3.0,iocharset=utf8,uid=$UID_PG,gid=$GID_WWW,file_mode=0660,dir_mode=0770" \
    >>"$LOG" 2>&1 || log "ERROR: cannot mount $UNC"
  TARGET="$MOUNT"
fi

mkdir -p "$TARGET" 2>/dev/null

LIST=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" \
        --cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}" 2>/dev/null \
       | awk -F' *: *' '/^name/{print $2}')
[ -n "$LIST" ] || LIST=""

STAMP=$(date +%Y%m%d-%H%M)
OK=0
FAIL=0
FILES=""

SKIP=$(python3 - <<'PY'
import sqlite3
try:
    c = sqlite3.connect('/opt/1c-portal/portal.db')
    print(' '.join(r[0] for r in c.execute("select slug from bases where coalesce(is_sandbox,0)=1")))
except Exception:
    print('')
PY
)
# список исключений: сломанные/устаревшие инфобазы (ждут удаления в 1С)
SKIP_FILE=/etc/1c-portal/backup-skip.txt
if [ -f "$SKIP_FILE" ]; then
  SKIP="$SKIP $(grep -vE '^\s*#|^\s*$' "$SKIP_FILE" | tr '\n' ' ')"
fi
for NAME in $LIST; do
  case " $SKIP " in *" $NAME "*) log "$NAME пропущена (песочница)"; continue;; esac
  DB=$($RAC "$RAS" infobase info --cluster="$CLUSTER" --name="$NAME" \
         --cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}" 2>/dev/null \
       | awk -F' *: *' '/^db-name/{print $2; exit}')
  # если прав на infobase info нет — берём соответствие из карты портала
  if [ -z "$DB" ] && [ -f /etc/1c-portal/backup-map.txt ]; then
    DB=$(awk -F= -v n="$NAME" '$1==n {print $2; exit}' /etc/1c-portal/backup-map.txt)
  fi
  [ -n "$DB" ] || DB="$NAME"
  OUT="$TARGET/$NAME-$STAMP.dump"
  ionice -c3 nice -n 10 su -s /bin/bash postgres -c "pg_dump -Fc -d '$DB' -f '$OUT'" >>"$LOG" 2>&1
  if [ -s "$OUT" ]; then
    log "$NAME ($DB) ok $(du -h "$OUT" | cut -f1)"
    OK=$((OK+1))
    FILES="$FILES $NAME-$STAMP.dump"
  else
    log "$NAME ($DB) FAILED"
    FAIL=$((FAIL+1))
    rm -f "$OUT"
  fi
done

for NAME in $LIST; do
  ls -1t "$TARGET/$NAME-"*.dump 2>/dev/null | tail -n +$((KEEP+1)) | while read -r old; do
    rm -f "$old"
    log "removed old: $(basename "$old")"
  done
done

FREE=$(df -h "$TARGET" 2>/dev/null | awk 'NR==2{print $4" free of "$2}')
log "done: ok $OK, failed $FAIL, target $TARGET ($FREE)"

# индекс копий: портал читает его, даже если каталог ему недоступен
python3 - "$TARGET" <<'PY'
import json, os, time
target = __import__('sys').argv[1]
items = []
try:
    for name in sorted(os.listdir(target)):
        if not name.endswith('.dump'):
            continue
        path = os.path.join(target, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        base = name.split('-')[0]
        items.append({
            'name': name,
            'path': path,
            'base': base,
            'size': st.st_size,
            'when': time.strftime('%d.%m.%Y %H:%M', time.localtime(st.st_mtime)),
        })
except OSError:
    pass
try:
    json.dump({'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': items},
              open('/etc/1c-portal/backup-files.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    os.chmod('/etc/1c-portal/backup-files.json', 0o644)
except Exception:
    pass
PY

python3 - "$STATUS" "$TARGET" "$OK" "$FAIL" "$FILES" "$FREE" <<'PY'
import json, sys, time
status = {
    'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'target': sys.argv[2],
    'ok': int(sys.argv[3]),
    'failed': int(sys.argv[4]),
    'files': sys.argv[5].split(),
    'free': sys.argv[6],
}
try:
    json.dump(status, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
except Exception:
    pass
PY