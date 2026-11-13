#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHECK="$ROOT/check-hasp-rac-license.sh"

printf 'process : uuid\nlicense-type: HASP\nissued-by-server: yes\n' | bash "$CHECK"
printf 'OK: accepts compact RAC license fields\n'

printf 'license-type : HASP\nissued-by-server : yes\n' | bash "$CHECK"
printf 'OK: accepts RAC fields with whitespace\n'

expect_reject() {
  if printf '%s\n' "$1" | bash "$CHECK"; then
    printf 'FAIL: accepted invalid RAC license response\n' >&2
    exit 1
  fi
}

expect_reject 'license-type: HASP'
expect_reject 'license-type: Software; issued-by-server: yes'
expect_reject 'license-type: HASP; issued-by-server: no'
printf 'OK: rejects missing, wrong-type, and non-server-issued licenses\n'

printf 'ALL RAC LICENSE GUARD TESTS PASSED\n'