#!/bin/bash
set -uo pipefail
BIN=/opt/1cv8/x86_64/8.3.27.1989/1cv8
echo "=== заливаю .dt в demo через xvfb ==="
xvfb-run -a "$BIN" DESIGNER /S"127.0.0.1/demo" /N"Администратор" /P"" \
  /RestoreIB /tmp/podolsky-1Cv8.dt /Out/tmp/restore-demo.log 2>&1 | tail -10
echo "  код: ${PIPESTATUS[0]}"
echo "=== лог 1С ==="
tail -6 /tmp/restore-demo.log 2>/dev/null | sed 's/^/  /'
echo "=== данные в demo ==="
su -s /bin/bash postgres -c "psql -Atc \"select pg_size_pretty(pg_database_size('demo'))\"" | sed 's/^/  размер: /'
su -s /bin/bash postgres -c "psql -d demo -Atc \"select count(*) from v8users\"" 2>/dev/null | sed 's/^/  пользователей 1С: /'
su -s /bin/bash postgres -c "psql -d demo -Atc \"select count(*) from _reference100\"" 2>/dev/null | sed 's/^/  _reference100: /'
su -s /bin/bash postgres -c "psql -d demo -Atc \"select count(*) from _document713\"" 2>/dev/null | sed 's/^/  _document713: /'
