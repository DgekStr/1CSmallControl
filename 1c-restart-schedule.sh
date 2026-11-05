#!/bin/bash
# Управляет расписанием автоматического перезапуска сервера 1С.
# Использование: 1c-restart-schedule "0 3 * * *" | off | status
set -uo pipefail

FILE=/etc/cron.d/1c-safe-restart
MODE="${1:-status}"

case "$MODE" in
  off)
    rm -f "$FILE"
    echo "расписание отключено"
    ;;
  status)
    if [ -f "$FILE" ]; then
      grep -v '^#' "$FILE" | grep -v '^$' | tail -1
    else
      echo "off"
    fi
    ;;
  *)
    SCHEDULE="$MODE"
    echo "# автоматический перезапуск сервера 1С (создано порталом)" > "$FILE"
    echo "$SCHEDULE root /usr/local/bin/1c-safe-restart apply >> /var/log/1c-safe-restart.log 2>&1" >> "$FILE"
    chmod 644 "$FILE"
    echo "расписание установлено: $SCHEDULE"
    ;;
esac
