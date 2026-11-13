#!/bin/bash
set -u

LSUSB=${HASP_LSUSB:-/usr/bin/lsusb}
SLEEP=${HASP_SLEEP:-/bin/sleep}
LOGGER=${HASP_LOGGER:-/usr/bin/logger}
EXPECTED_DEVICES=${HASP_EXPECTED_DEVICES:-3}
ATTEMPTS=${HASP_READY_ATTEMPTS:-30}

[[ "$EXPECTED_DEVICES" =~ ^[1-9][0-9]*$ ]] || EXPECTED_DEVICES=3
[[ "$ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || ATTEMPTS=30

for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  count=$("$LSUSB" -d 0529:0001 2>/dev/null | wc -l)
  if [ "$count" -ge "$EXPECTED_DEVICES" ]; then
    "$LOGGER" -t usbhasp-wait-ready "HASP USB devices ready: $count"
    exit 0
  fi
  "$SLEEP" 1
done

"$LOGGER" -p daemon.err -t usbhasp-wait-ready \
  "HASP USB readiness timeout: expected $EXPECTED_DEVICES, found ${count:-0}"
exit 1