#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/1c-cluster-health.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
mkdir -p "$BIN"

cat > "$BIN/mock" <<'MOCK'
#!/bin/bash
cmd=${0##*/}
case "$cmd" in
  ss)
    [ "${HEALTH_TEST_PORT:-1}" = 1 ] && printf 'LISTEN 0 128 0.0.0.0:1541\n'
    ;;
  pgrep)
    process=${!#}
    case "$process" in
      rmngr) [ "${HEALTH_TEST_RMNGR:-1}" = 1 ] ;;
      rphost)
        if [ -f "${HEALTH_TEST_ACTIONS:-}" ] && grep -q 'restart srv1cv8' "$HEALTH_TEST_ACTIONS"; then
          exit 0
        fi
        [ "${HEALTH_TEST_RPHOST:-1}" = 1 ]
        ;;
      *) exit 1 ;;
    esac
    ;;
  timeout)
    shift
    exec "$@"
    ;;
  rac)
    [ "${HEALTH_TEST_RAC:-1}" = 1 ] && printf 'name : test\n'
    ;;
  systemctl)
    case "${1:-}" in
      show) printf '0\n' ;;
      is-active) printf 'active\n' ;;
      restart) printf '%s\n' "$*" >> "$HEALTH_TEST_ACTIONS" ;;
      *) exit 0 ;;
    esac
    ;;
  flock)
    [ "${HEALTH_TEST_LOCK_BUSY:-0}" = 0 ]
    ;;
  sleep|curl)
    exit 0
    ;;
  *) exit 2 ;;
esac
MOCK
chmod +x "$BIN/mock"
for command in ss pgrep timeout rac systemctl flock sleep curl; do
  ln -s mock "$BIN/$command"
done

export PATH="$BIN:$PATH"
export IC_RAC="$BIN/rac"
export IC_CLUSTER=test-cluster IC_CLUSTER_USER=test-user IC_CLUSTER_PWD=test-password
export IC_HEALTH_CONF="$TMP/session-admin.conf"
export IC_HEALTH_HOOK_FILE="$TMP/no-hook"
export IC_HEALTH_LOG="$TMP/health.log"
export IC_HEALTH_STATE_DIR="$TMP/state"
export IC_RESTART_LOCK="$TMP/restart.lock"
export HEALTH_TEST_ACTIONS="$TMP/actions"
: > "$IC_HEALTH_CONF"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
pass() { printf 'OK: %s\n' "$1"; }
reset_state() {
  rm -rf "$IC_HEALTH_STATE_DIR"
  : > "$HEALTH_TEST_ACTIONS"
  : > "$IC_HEALTH_LOG"
}
run_health() { bash "$SCRIPT"; }
assert_no_restart() {
  if grep -q 'restart ' "$HEALTH_TEST_ACTIONS"; then fail "$1 unexpectedly restarted a service"; fi
}

reset_state
run_health
assert_no_restart "healthy probe"
pass "healthy probe makes no restart"
if grep -q '1c-heal-bases' "$SCRIPT"; then fail "healthcheck must not run password-heal automatically"; fi
pass "healthcheck never invokes password-heal"

reset_state
export HEALTH_TEST_RAC=0 HEALTH_TEST_PORT=1 HEALTH_TEST_RMNGR=1 HEALTH_TEST_RPHOST=1
run_health
[ "$(cat "$IC_HEALTH_STATE_DIR/failures")" = 1 ] || fail "first RAC failure was not counted"
run_health
assert_no_restart "RAC-only failure"
grep -q 'автоматический перезапуск запрещён' "$IC_HEALTH_LOG" || fail "RAC-only failure was not classified"
pass "RAC-only failure is debounced and never restarts the cluster"

reset_state
export HEALTH_TEST_RAC=1 HEALTH_TEST_RPHOST=0
run_health
assert_no_restart "first missing-rphost probe"
run_health
grep -q 'restart srv1cv8' "$HEALTH_TEST_ACTIONS" || fail "confirmed rphost failure did not restart srv1cv8"
if grep -q 'restart ras.service' "$HEALTH_TEST_ACTIONS"; then fail "healthcheck restarted RAS"; fi
[ ! -e "$IC_HEALTH_STATE_DIR/failures" ] || fail "successful recovery did not clear the incident"
pass "two confirmed core failures trigger one srv1cv8 restart and recover"

reset_state
export HEALTH_TEST_RPHOST=0 HEALTH_TEST_LOCK_BUSY=1
run_health
[ ! -e "$IC_HEALTH_STATE_DIR/failures" ] || fail "locked maintenance interval changed incident state"
assert_no_restart "held maintenance lock"
pass "maintenance lock suppresses the healthcheck"

set +e
HEALTH_TEST_LOCK_BUSY=1 IC_RESTART_LOCK="$TMP/restart.lock" \
  bash "$ROOT/1c-safe-restart.sh" apply > "$TMP/safe-restart.out" 2>&1
safe_restart_status=$?
set -e
[ "$safe_restart_status" = 75 ] || fail "safe-restart did not refuse a held maintenance lock"
pass "manual safe-restart and healthcheck share the same lock"

reset_state
export HEALTH_TEST_LOCK_BUSY=0 HEALTH_TEST_RPHOST=0
run_health || true
run_health || true
[ "$(grep -c 'restart srv1cv8' "$HEALTH_TEST_ACTIONS")" = 1 ] || fail "failed recovery was retried without operator intervention"
pass "failed recovery is attempted only once per incident"

printf 'ALL HEALTHCHECK TESTS PASSED\n'