#!/bin/bash
# 1c-kick-all <база> [база...] — отключает сеансы во всех указанных базах 1С.
set -uo pipefail
[ $# -ge 1 ] || { echo "usage: 1c-kick-all <base> [base...]"; exit 64; }
total=0
for b in "$@"; do
  echo "== $b"
  out=$(/usr/local/bin/1c-kick-sessions "$b" 2>&1)
  echo "$out"
  n=$(printf '%s' "$out" | sed -n 's/.*отключено сеансов: \([0-9]\+\).*/\1/p' | head -1)
  [ -n "$n" ] && total=$((total + n))
done
echo "итого отключено сеансов: $total"
