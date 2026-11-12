#!/bin/bash
# Консервативная проверка кластера 1С с одной попыткой восстановления на инцидент.
set -uo pipefail

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
LOG=${IC_HEALTH_LOG:-/var/log/1c-cluster-health.log}
CONF=${IC_HEALTH_CONF:-/etc/1c-portal/1c-session-admin.conf}
HOOK_FILE=${IC_HEALTH_HOOK_FILE:-/etc/1c-portal/mm-hook}
STATE_DIR=${IC_HEALTH_STATE_DIR:-/run/1c-cluster-health}
RESTART_LOCK=${IC_RESTART_LOCK:-/var/run/1c-restart.lock}
FAILURE_THRESHOLD=${IC_HEALTH_FAILURE_THRESHOLD:-2}
STARTUP_GRACE_SECONDS=${IC_HEALTH_STARTUP_GRACE:-180}
READY_TIMEOUT_SECONDS=${IC_HEALTH_READY_TIMEOUT:-180}

[[ "$FAILURE_THRESHOLD" =~ ^[1-9][0-9]*$ ]] || FAILURE_THRESHOLD=2
[[ "$STARTUP_GRACE_SECONDS" =~ ^[0-9]+$ ]] || STARTUP_GRACE_SECONDS=180
[[ "$READY_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || READY_TIMEOUT_SECONDS=180

FAILURE_FILE="$STATE_DIR/failures"
RESTARTED_FILE="$STATE_DIR/restart-attempted"
ALERT_FILE="$STATE_DIR/alert-sent"
HOOK=$(cat "$HOOK_FILE" 2>/dev/null || true)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

if ! mkdir -p "$STATE_DIR"; then
  log "ОШИБКА: не удалось создать каталог состояния $STATE_DIR"
  exit 1
fi
if ! { exec 9>"$RESTART_LOCK"; } 2>/dev/null; then
  log "ОШИБКА: не удалось открыть lock-файл перезапуска"
  exit 1
fi
if ! flock -n 9; then
  exit 0
fi

notify_once() {
  local message=$1 body
  [ -n "$HOOK" ] || return 0
  [ -e "$ALERT_FILE" ] && return 0
  : > "$ALERT_FILE"
  body=$(printf '{"text":"%s"}' "$message")
  curl --max-time 5 -s -o /dev/null -H 'Content-Type: application/json' \
    -d "$body" "$HOOK" 2>/dev/null || true
}

port_ok() { ss -H -ltn 'sport = :1541' 2>/dev/null | grep -q .; }
rmngr_ok() { pgrep -x rmngr >/dev/null 2>&1; }
work_ok() { pgrep -x rphost >/dev/null 2>&1; }
rac_ok() {
  [ -r "$CONF" ] || return 1
  # shellcheck disable=SC1090
  . "$CONF" 2>/dev/null || return 1
  [ -n "${IC_CLUSTER:-}" ] || return 1
  timeout 10 "$RAC" 127.0.0.1:1545 infobase summary list \
    --cluster="$IC_CLUSTER" --cluster-user="${IC_CLUSTER_USER:-}" \
    --cluster-pwd="${IC_CLUSTER_PWD:-}" 2>/dev/null | grep -q '^name'
}

probe() {
  PORT_OK=0; RMNGR_OK=0; WORK_OK=0; RAC_OK=0
  port_ok && PORT_OK=1
  rmngr_ok && RMNGR_OK=1
  work_ok && WORK_OK=1
  rac_ok && RAC_OK=1
}

healthy() { [ "$PORT_OK$RMNGR_OK$WORK_OK$RAC_OK" = 1111 ]; }

in_startup_grace() {
  local started uptime elapsed
  started=$(systemctl show -p ActiveEnterTimestampMonotonic --value srv1cv8 2>/dev/null || true)
  [[ "$started" =~ ^[0-9]+$ ]] && [ "$started" -gt 0 ] || return 1
  uptime=$(awk '{printf "%.0f", $1 * 1000000}' /proc/uptime)
  elapsed=$((uptime - started))
  (( elapsed >= 0 && elapsed < STARTUP_GRACE_SECONDS * 1000000 ))
}

clear_incident() {
  rm -f "$FAILURE_FILE" "$RESTARTED_FILE" "$ALERT_FILE"
}

probe
if healthy; then
  if [ -e "$FAILURE_FILE" ] || [ -e "$RESTARTED_FILE" ]; then
    log "Кластер восстановился; состояние инцидента очищено"
  fi
  clear_incident
  exit 0
fi

status="1541=$PORT_OK rmngr=$RMNGR_OK rphost=$WORK_OK rac=$RAC_OK"
if in_startup_grace; then
  rm -f "$FAILURE_FILE"
  log "штатный запуск, действует grace-период: $status"
  exit 0
fi

failures=0
if [ -r "$FAILURE_FILE" ]; then
  read -r failures < "$FAILURE_FILE" || failures=0
fi
[[ "$failures" =~ ^[0-9]+$ ]] || failures=0
failures=$((failures + 1))
printf '%s\n' "$failures" > "$FAILURE_FILE.tmp.$$"
mv -f "$FAILURE_FILE.tmp.$$" "$FAILURE_FILE"
log "проверка кластера не пройдена ($failures/$FAILURE_THRESHOLD): $status"

if [ "$failures" -lt "$FAILURE_THRESHOLD" ]; then
  exit 0
fi

# RAC-only сбой не доказывает отказ ragent и не является основанием для рестарта.
if [ "$PORT_OK$RMNGR_OK$WORK_OK" = 111 ] && [ "$RAC_OK" = 0 ]; then
  log "RAC не отвечает при работающих процессах; автоматический перезапуск запрещён"
  notify_once "#### 1C Small Control · RAC недоступен\n\nПорт 1541, rmngr и rphost работают; автоматический перезапуск кластера не выполнялся. Нужна проверка RAS/RAC."
  exit 0
fi

if [ -e "$RESTARTED_FILE" ]; then
  log "автоперезапуск уже выполнялся для этого инцидента; повтор запрещён"
  notify_once "#### 1C Small Control · кластер 1С не восстановлен\n\nПосле одной попытки перезапуска компоненты кластера остаются недоступны. Нужен ручной разбор."
  exit 0
fi

: > "$RESTARTED_FILE"
log "однократный перезапуск srv1cv8 после подтверждённых сбоев"
systemctl restart srv1cv8 >> "$LOG" 2>&1 || log "systemctl restart srv1cv8 завершился ошибкой"

deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  sleep 3
  probe
  if healthy; then
    log "кластер восстановлен после одного перезапуска srv1cv8"
    clear_incident
    exit 0
  fi
done

log "кластер не готов после перезапуска; повторная попытка до восстановления запрещена"
notify_once "#### 1C Small Control · кластер 1С не восстановлен\n\nПорт 1541/rmngr/rphost/RAC не готовы после одной попытки перезапуска. Нужен ручной разбор."
exit 1
