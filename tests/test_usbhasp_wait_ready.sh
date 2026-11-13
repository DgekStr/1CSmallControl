#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/usbhasp-wait-ready.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/lsusb" <<'MOCK'
#!/bin/bash
for ((index = 0; index < ${HASP_TEST_USB_COUNT:-0}; index++)); do
  printf 'Bus 002 Device %03d: ID 0529:0001 Aladdin HASP\n' "$((index + 2))"
done
MOCK
cat > "$TMP/noop" <<'MOCK'
#!/bin/bash
exit 0
MOCK
cat > "$TMP/logger" <<'MOCK'
#!/bin/bash
printf '%s\n' "$*" >> "$HASP_TEST_LOG"
MOCK
chmod +x "$TMP/lsusb" "$TMP/noop" "$TMP/logger"

export HASP_LSUSB="$TMP/lsusb"
export HASP_SLEEP="$TMP/noop"
export HASP_LOGGER="$TMP/logger"
export HASP_READY_ATTEMPTS=2
export HASP_TEST_LOG="$TMP/log"

HASP_TEST_USB_COUNT=3 bash "$SCRIPT"
grep -q 'HASP USB devices ready: 3' "$HASP_TEST_LOG"
printf 'OK: readiness succeeds when all three devices are enumerated\n'

: > "$HASP_TEST_LOG"
set +e
HASP_TEST_USB_COUNT=2 bash "$SCRIPT"
status=$?
set -e
[ "$status" = 1 ]
grep -q 'expected 3, found 2' "$HASP_TEST_LOG"
printf 'OK: readiness fails closed when the 100-user device set is incomplete\n'

printf 'ALL USBHASP READINESS TESTS PASSED\n'