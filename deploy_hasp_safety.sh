#!/bin/bash
set -euo pipefail

STAGE=${1:?usage: deploy_hasp_safety.sh <staging-directory>}
WAIT_SRC="$STAGE/usbhasp-wait-ready.sh"
LICENSE_CHECK_SRC="$STAGE/check-hasp-rac-license.sh"
USBHASPD_DROPIN_SRC="$STAGE/wait-usb-keys.conf"
AKSUSBD_DROPIN_SRC="$STAGE/usbhaspd-order.conf"
HASPLM_DROPIN_SRC="$STAGE/aksusbd-order.conf"
ROTATE_SRC="$STAGE/hasplm-error"
USBHASPD_DROPIN_DIR=/etc/systemd/system/usbhaspd.service.d
USBHASPD_DROPIN="$USBHASPD_DROPIN_DIR/wait-usb-keys.conf"
AKSUSBD_DROPIN_DIR=/etc/systemd/system/aksusbd.service.d
AKSUSBD_DROPIN="$AKSUSBD_DROPIN_DIR/usbhaspd-order.conf"
HASPLM_DROPIN_DIR=/etc/systemd/system/hasplm.service.d
HASPLM_DROPIN="$HASPLM_DROPIN_DIR/aksusbd-order.conf"
WAIT=/usr/local/sbin/usbhasp-wait-ready
ROTATE=/etc/logrotate.d/hasplm-error
KEY=/etc/usbhaspd/keys/BFC2B1DE-net100.json
CONF=/etc/1c-portal/1c-session-admin.conf
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
LOG=/var/hasplm/error.log
INSTALLED_WAIT=0
INSTALLED_USBHASPD_DROPIN=0
INSTALLED_AKSUSBD_DROPIN=0
INSTALLED_HASPLM_DROPIN=0
INSTALLED_ROTATE=0
PHASE=preflight

file_hash() { sha256sum "$1" | awk '{print $1}'; }
main_pid() { systemctl show "$1" -p MainPID --value; }
rac_has_server_hasp_license() {
  printf '%s\n' "$1" | bash "$LICENSE_CHECK_SRC"
}
rollback() {
  rc=$?
  if [ "$INSTALLED_WAIT" = 1 ]; then rm -f "$WAIT"; fi
  if [ "$INSTALLED_USBHASPD_DROPIN" = 1 ]; then rm -f "$USBHASPD_DROPIN"; fi
  if [ "$INSTALLED_AKSUSBD_DROPIN" = 1 ]; then rm -f "$AKSUSBD_DROPIN"; fi
  if [ "$INSTALLED_HASPLM_DROPIN" = 1 ]; then rm -f "$HASPLM_DROPIN"; fi
  if [ "$INSTALLED_ROTATE" = 1 ]; then rm -f "$ROTATE"; fi
  if [ "$INSTALLED_WAIT" = 1 ] || [ "$INSTALLED_USBHASPD_DROPIN" = 1 ] || \
     [ "$INSTALLED_AKSUSBD_DROPIN" = 1 ] || [ "$INSTALLED_HASPLM_DROPIN" = 1 ] || \
     [ "$INSTALLED_ROTATE" = 1 ]; then
    systemctl daemon-reload || true
    printf '%s exit=%s\n' "$PHASE" "$rc" > "$BACKUP/rollback.txt"
    echo "Configuration rolled back at phase $PHASE (exit=$rc); preserved backup at $BACKUP" >&2
  fi
  exit "$rc"
}

[ "$(id -u)" = 0 ] || { echo 'Run this script through sudo.' >&2; exit 1; }
[ -f "$WAIT_SRC" ] && [ -f "$LICENSE_CHECK_SRC" ] && [ -f "$USBHASPD_DROPIN_SRC" ] && \
  [ -f "$AKSUSBD_DROPIN_SRC" ] && [ -f "$HASPLM_DROPIN_SRC" ] && [ -f "$ROTATE_SRC" ]
[ -x "$RAC" ] && [ -r "$CONF" ] && [ -r "$KEY" ] && [ -f "$LOG" ]
[ ! -e "$WAIT" ] || { echo "Existing readiness helper found: $WAIT; refusing to overwrite." >&2; exit 2; }
[ ! -e "$USBHASPD_DROPIN" ] || { echo "Existing drop-in found: $USBHASPD_DROPIN; refusing to overwrite." >&2; exit 2; }
[ ! -e "$AKSUSBD_DROPIN" ] || { echo "Existing drop-in found: $AKSUSBD_DROPIN; refusing to overwrite." >&2; exit 2; }
[ ! -e "$HASPLM_DROPIN" ] || { echo "Existing drop-in found: $HASPLM_DROPIN; refusing to overwrite." >&2; exit 2; }
[ ! -e "$ROTATE" ] || { echo "Existing logrotate rule found: $ROTATE; refusing to overwrite." >&2; exit 3; }
command -v flock >/dev/null
command -v logrotate >/dev/null

for unit in aksusbd.service usbhaspd.service hasplm.service srv1cv8.service ras.service; do
  systemctl is-active --quiet "$unit" || { echo "$unit is not active; refusing deployment." >&2; exit 4; }
done
pgrep -x rmngr >/dev/null
pgrep -x rphost >/dev/null
ss -H -ltn 'sport = :1541' | grep -q .

exec 9>/var/run/1c-restart.lock
flock -n 9 || { echo 'Maintenance/restart lock is busy; refusing deployment.' >&2; exit 75; }

# Keep a private recovery copy of the 100-user key before touching system config.
PHASE=backup-key
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=/var/backups/1c-hasp-safety-$STAMP
install -d -o root -g root -m 700 "$BACKUP"
install -o root -g root -m 600 "$KEY" "$BACKUP/net100-key.json"
KEY_HASH=$(file_hash "$KEY")
printf '%s\n' "$KEY_HASH" > "$BACKUP/net100-key.sha256"

. "$CONF"
PHASE=precheck-rac-license
RAC_BEFORE=$("$RAC" 127.0.0.1:1545 process list --cluster="$IC_CLUSTER" \
  --cluster-user="$IC_CLUSTER_USER" --cluster-pwd="$IC_CLUSTER_PWD" --licenses 2>&1)
rac_has_server_hasp_license "$RAC_BEFORE" || {
  echo 'RAC does not report a HASP license; refusing deployment.' >&2
  printf '%s\n' "$RAC_BEFORE" | awk -F: 'tolower($1) ~ /license-type|issued-by-server/ {print $1 ": <value-present>"}' >&2
  exit 5
}

PID_USBHASPD=$(main_pid usbhaspd.service)
PID_AKSUSBD=$(main_pid aksusbd.service)
PID_HASPLM=$(main_pid hasplm.service)
PID_1C=$(main_pid srv1cv8.service)
PID_RAS=$(main_pid ras.service)

install -d -o root -g root -m 755 "$USBHASPD_DROPIN_DIR" "$AKSUSBD_DROPIN_DIR" "$HASPLM_DROPIN_DIR"
trap rollback EXIT
PHASE=install-config
INSTALLED_WAIT=1
install -o root -g root -m 755 "$WAIT_SRC" "$WAIT.new.$$"
mv "$WAIT.new.$$" "$WAIT"
INSTALLED_USBHASPD_DROPIN=1
install -o root -g root -m 644 "$USBHASPD_DROPIN_SRC" "$USBHASPD_DROPIN.new.$$"
mv "$USBHASPD_DROPIN.new.$$" "$USBHASPD_DROPIN"
INSTALLED_AKSUSBD_DROPIN=1
install -o root -g root -m 644 "$AKSUSBD_DROPIN_SRC" "$AKSUSBD_DROPIN.new.$$"
mv "$AKSUSBD_DROPIN.new.$$" "$AKSUSBD_DROPIN"
INSTALLED_HASPLM_DROPIN=1
install -o root -g root -m 644 "$HASPLM_DROPIN_SRC" "$HASPLM_DROPIN.new.$$"
mv "$HASPLM_DROPIN.new.$$" "$HASPLM_DROPIN"
INSTALLED_ROTATE=1
install -o root -g root -m 644 "$ROTATE_SRC" "$ROTATE.new.$$"
mv "$ROTATE.new.$$" "$ROTATE"

PHASE=systemd-verify
if ! systemd-analyze verify usbhaspd.service aksusbd.service hasplm.service \
  > "$BACKUP/systemd-verify.txt" 2>&1; then
  cat "$BACKUP/systemd-verify.txt" >&2
  exit 31
fi
PHASE=logrotate-dry-run
if ! logrotate --debug --state "$BACKUP/logrotate.status" "$ROTATE" \
  > "$BACKUP/logrotate-dry-run.txt" 2>&1; then
  cat "$BACKUP/logrotate-dry-run.txt" >&2
  exit 32
fi
PHASE=systemd-daemon-reload
systemctl daemon-reload

PHASE=unit-property-check
USBHASPD_EXEC_POST=$(systemctl show usbhaspd.service -p ExecStartPost --value)
AKSUSBD_AFTER=$(systemctl show aksusbd.service -p After --value)
AKSUSBD_REQUIRES=$(systemctl show aksusbd.service -p Requires --value)
HASPLM_AFTER=$(systemctl show hasplm.service -p After --value)
HASPLM_REQUIRES=$(systemctl show hasplm.service -p Requires --value)
{
  printf 'usbhaspd ExecStartPost: %s\n' "$USBHASPD_EXEC_POST"
  printf 'aksusbd After: %s\nRequires: %s\n' "$AKSUSBD_AFTER" "$AKSUSBD_REQUIRES"
  printf 'hasplm After: %s\nRequires: %s\n' "$HASPLM_AFTER" "$HASPLM_REQUIRES"
} > "$BACKUP/systemd-properties.txt"
if [[ "$USBHASPD_EXEC_POST" != *"$WAIT"* ]]; then echo 'ExecStartPost check failed' >&2; exit 41; fi
if [[ " $AKSUSBD_AFTER " != *" usbhaspd.service "* ]]; then echo 'aksusbd After check failed' >&2; exit 42; fi
if [[ " $AKSUSBD_REQUIRES " != *" usbhaspd.service "* ]]; then echo 'aksusbd Requires check failed' >&2; exit 43; fi
if [[ " $HASPLM_AFTER " != *" aksusbd.service "* ]]; then echo 'hasplm After check failed' >&2; exit 44; fi
if [[ " $HASPLM_REQUIRES " != *" aksusbd.service "* ]]; then echo 'hasplm Requires check failed' >&2; exit 45; fi

PHASE=service-state-check
for unit in aksusbd.service usbhaspd.service hasplm.service srv1cv8.service ras.service; do
  systemctl is-active --quiet "$unit"
done
[ "$(main_pid usbhaspd.service)" = "$PID_USBHASPD" ]
[ "$(main_pid aksusbd.service)" = "$PID_AKSUSBD" ]
[ "$(main_pid hasplm.service)" = "$PID_HASPLM" ]
[ "$(main_pid srv1cv8.service)" = "$PID_1C" ]
[ "$(main_pid ras.service)" = "$PID_RAS" ]
[ "$(file_hash "$KEY")" = "$KEY_HASH" ]

PHASE=postcheck-rac-license
RAC_AFTER=$("$RAC" 127.0.0.1:1545 process list --cluster="$IC_CLUSTER" \
  --cluster-user="$IC_CLUSTER_USER" --cluster-pwd="$IC_CLUSTER_PWD" --licenses 2>&1)
rac_has_server_hasp_license "$RAC_AFTER"
journalctl -b -u usbhaspd.service --no-pager -o cat \
  | grep -Fq "Loaded key 2: 'ORGL8: 100 Users'"

PHASE=complete
INSTALLED_WAIT=0
INSTALLED_USBHASPD_DROPIN=0
INSTALLED_AKSUSBD_DROPIN=0
INSTALLED_HASPLM_DROPIN=0
INSTALLED_ROTATE=0
trap - EXIT
printf 'DEPLOY_OK backup=%s\n' "$BACKUP"
printf '100-user-key-sha256=%s\n' "$KEY_HASH"
printf 'Service PIDs unchanged; no HASP or 1C service was restarted.\n'