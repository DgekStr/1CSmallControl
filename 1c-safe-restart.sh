#!/bin/bash
# Безопасный перезапуск сервера 1С: сначала завершает сеансы, затем перезапускает
# службу и проверяет, что кластер и базы снова доступны.
#
# Использование:
#   ./1c-safe-restart.sh check   — только показать состояние (ничего не меняет)
#   ./1c-safe-restart.sh apply   — завершить сеансы и перезапустить службу
set -uo pipefail

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CLUSTER_DEFAULT=e3220a07-7374-4fc0-b4fb-25ace3789930
MODE=${1:-check}

cluster_uuid() {
  "$RAC" "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}'
}

sessions_total() {
  local c
  c=$(cluster_uuid)
  [ -z "$c" ] && { echo 0; return; }
  "$RAC" "$RAS" session list --cluster="$c" 2>/dev/null | grep -c '^session '
}

sessions_by_app() {
  local c
  c=$(cluster_uuid)
  [ -z "$c" ] && return
  "$RAC" "$RAS" session list --cluster="$c" 2>/dev/null | awk -F' *: *' '/^app-id/{print $2}' | sort | uniq -c
}

check_state() {
  echo "служба srv1cv8: $(systemctl is-active srv1cv8)"
  echo "кластер:         $(cluster_uuid || echo нет)"
  echo "сеансов всего:   $(sessions_total)"
  echo "по клиентам:"
  sessions_by_app | sed 's/^/  /'
}

wait_ready() {
  for _ in $(seq 1 60); do
    if systemctl is-active --quiet srv1cv8 && [ -n "$(cluster_uuid)" ]; then
      sleep 3
      return 0
    fi
    sleep 2
  done
  return 1
}

case "$MODE" in
  check)
    check_state
    ;;
  apply)
    echo "== до перезапуска =="
    check_state

    echo
    echo "== завершаю сеансы =="
    if [ -x /usr/local/bin/1c-kick-sessions ]; then
      for base in base1 base2; do
        /usr/local/bin/1c-kick-sessions "$base" 2>/dev/null | tail -1 | sed "s/^/  $base: /"
      done
    else
      echo "  скрипт 1c-kick-sessions не найден — пропускаю"
    fi
    sleep 2

    echo
    echo "== перезапуск srv1cv8 =="
    systemctl restart srv1cv8
    if wait_ready; then
      echo "  служба поднялась"
    else
      echo "  ОШИБКА: служба не поднялась за 2 минуты"
      journalctl -u srv1cv8 -n 20 --no-pager
      exit 1
    fi

    echo
    echo "== после перезапуска =="
    check_state
    echo
    echo "проверка публикации:"
    curl -s -o /dev/null -w '  /WEB/base1/ = %{http_code}\n' --resolve 1c.dgek.ru:8081:127.0.0.1 http://127.0.0.1:8081/WEB/base1/
    ;;
  *)
    echo "usage: $0 check|apply"
    exit 64
    ;;
esac
