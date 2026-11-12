#!/bin/bash
# 1c-cluster-health — проверка и авто-восстановление кластера 1С.
# Запускается таймером; при сбое перезапускает srv1cv8/ras и пишет журнал.
set -uo pipefail
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
LOG=/var/log/1c-cluster-health.log
CONF=/etc/1c-portal/1c-session-admin.conf
HOOK=$(cat /etc/1c-portal/mm-hook 2>/dev/null || true)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

port_ok() { [ "$(ss -ltn 2>/dev/null | grep -c ':1541 ')" -gt 0 ]; }
rmngr_ok() { [ "$(pgrep -c rmngr 2>/dev/null)" -gt 0 ]; }
work_ok() { [ "$(pgrep -c rphost 2>/dev/null)" -gt 0 ]; }
rac_ok() {
  . "$CONF" 2>/dev/null || return 1
  timeout 10 "$RAC" 127.0.0.1:1545 infobase summary list \
    --cluster="$IC_CLUSTER" --cluster-user="$IC_CLUSTER_USER" \
    --cluster-pwd="$IC_CLUSTER_PWD" 2>/dev/null | grep -q '^name'
}

healthy() { port_ok && rmngr_ok && rac_ok && work_ok; }

if healthy; then
  exit 0
fi

log "ОБНАРУЖЕН СБОЙ: 1541=$(port_ok && echo ok || echo fail) rmngr=$(rmngr_ok && echo ok || echo fail) rac=$(rac_ok && echo ok || echo fail)"

# 1) восстановление кластера
if ! port_ok || ! rmngr_ok; then
  log "перезапуск srv1cv8"
  systemctl restart srv1cv8 2>/dev/null
  for i in $(seq 1 25); do port_ok && rmngr_ok && break; sleep 3; done
fi
# 2) восстановление ras, если rac не отвечает
if ! rac_ok; then
  log "перезапуск ras.service"
  systemctl restart ras.service 2>/dev/null
  sleep 8
fi
# 3) второй проход, если не помогло
if ! healthy; then
  log "второй проход: полный перезапуск"
  systemctl restart srv1cv8 2>/dev/null
  for i in $(seq 1 25); do port_ok && rmngr_ok && break; sleep 3; done
  systemctl restart ras.service 2>/dev/null
  sleep 8
fi

if healthy; then
  log "ВОССТАНОВЛЕНО"
  /usr/local/bin/1c-heal-bases >> "$LOG" 2>&1 || log "1c-heal-bases: есть ошибки"
  msg="#### ⚠️ 1C Small Control · кластер перезапущен автоматически\n\nСбой кластера 1С обнаружен и устранён: восстановлены порт 1541, rmngr, RAS.\nПроверьте базы в кабинете."
  body=$(printf '{"text":"%s"}' "$msg")
  [ -n "$HOOK" ] && curl -s -o /dev/null -H 'Content-Type: application/json' -d "$body" "$HOOK" 2>/dev/null
else
  log "НЕ УДАЛОСЬ ВОССТАНОВИТЬ"
  msg="#### ❌ 1C Small Control · кластер 1С не восстанавливается\n\nПорт 1541/rmngr/RAS не поднялись после двух попыток. Нужен ручной разбор."
  body=$(printf '{"text":"%s"}' "$msg")
  [ -n "$HOOK" ] && curl -s -o /dev/null -H 'Content-Type: application/json' -d "$body" "$HOOK" 2>/dev/null
  exit 1
fi
