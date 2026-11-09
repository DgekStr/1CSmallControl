#!/bin/bash
set -uo pipefail
cd /tmp
ls -la lictools.tar.gz 2>/dev/null | awk '{print "  архив:", $5, "байт"}'
tar -xzf lictools.tar.gz && echo "  tar.gz распакован"
ls -la /tmp/*.tar 2>/dev/null | awk '{print "  tar:", $9, $5}'
TAR=$(ls -1 /tmp/1c_enterprise_license_tools_*.tar 2>/dev/null | head -1)
if [ -n "$TAR" ]; then
  echo "=== состав пакета ==="
  tar -tf "$TAR" | head -40
fi
