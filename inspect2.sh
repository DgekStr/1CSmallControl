#!/bin/bash
set -uo pipefail
cd /tmp
echo "=== что появилось после распаковки ==="
ls -la /tmp | grep -iE 'license|1c_ent|\.tar$|^d' | head -15
echo "=== ищу внутренний tar ==="
TAR=$(find /tmp -maxdepth 2 -name '1c_enterprise_license_tools*.tar' 2>/dev/null | head -1)
echo "  найден: ${TAR:-нет}"
if [ -n "$TAR" ]; then
  echo "=== первые 40 записей ==="
  tar -tf "$TAR" 2>/dev/null | head -40
  echo "=== всего записей: $(tar -tf "$TAR" 2>/dev/null | wc -l) ==="
fi
