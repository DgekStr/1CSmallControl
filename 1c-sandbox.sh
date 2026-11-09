#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Песочница восстановления базы 1С.
#   1c-sandbox create <исходная_база> <новая_база> <путь_к_дампу> [пароль_роли]
#   1c-sandbox drop <новая_база>
#   1c-sandbox check <путь_к_дампу>
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
[ -f "$CONF" ] && . "$CONF"

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
AUTH=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")

mode="${1:-}"

cluster_get() { $RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}'; }

infobase_uuid() {
  local want="$1"
  $RAC "$RAS" infobase summary list --cluster="${CLUSTER:-}" \
      --cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}" 2>/dev/null \
    | awk -v want="$want" '
        /^infobase/ {uuid=$3}
        /^name/     {name=$3; if (name == want) {print uuid; exit}}'
}

check_dump() {
  local dump="$1"
  [ -f "$dump" ] || { echo "нет файла дампа: $dump"; return 2; }
  pg_restore -l "$dump" >/dev/null 2>&1 || { echo "дамп повреждён или не читается"; return 3; }
  echo "ok"
}

tables_count() { su -s /bin/bash postgres -c "psql -d $1 -Atc \"select count(*) from pg_tables where schemaname='public'\"" 2>/dev/null; }

cleanup_failed() {
  local db="$1" role="$2"
  [ -n "$db" ] || return 0
  # завершаем соединения и удаляем базу принудительно (PostgreSQL 13+)
  su -s /bin/bash postgres -c "psql -Atc \"select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db' and pid <> pg_backend_pid()\"" >/dev/null 2>&1
  su -s /bin/bash postgres -c "psql -c \"drop database if exists $db with (force)\"" >/dev/null 2>&1 \
    || su -s /bin/bash postgres -c "psql -c \"drop database if exists $db\"" >/dev/null 2>&1
  [ -n "$role" ] && su -s /bin/bash postgres -c "psql -c \"drop role if exists $role\"" >/dev/null 2>&1
  # отдаём отчёт, осталась ли база
  local left
  left=$(su -s /bin/bash postgres -c "psql -Atc \"select count(*) from pg_database where datname = '$db'\"" 2>/dev/null)
  if [ "${left:-0}" != "0" ]; then
    echo "        ВНИМАНИЕ: база $db не удалена (left=$left)"
    return 1
  fi
  return 0
}

case "$mode" in
  check)
    check_dump "${2:-}" || exit $?
    ;;

  create)
    SRC="${2:-}"; NEW="${3:-}"; DUMP="${4:-}"; RPWD="${5:-}"
    if [ -z "$SRC" ] || [ -z "$NEW" ] || [ -z "$DUMP" ]; then
      echo "usage: 1c-sandbox create <src> <new> <dump> [pwd]"; exit 64
    fi
    check_dump "$DUMP" >/dev/null || { echo "дамп не прошёл проверку"; exit 3; }

    CLUSTER=$(cluster_get)
    [ -n "$CLUSTER" ] || { echo "кластер 1С недоступен"; exit 2; }

    ROLE="usr_${NEW//[^a-zA-Z0-9_]/_}"
    PWD="${RPWD:-$(openssl rand -hex 12)}"

    echo "  [1/5] база PostgreSQL $NEW"
    cleanup_failed "$NEW" "$ROLE"
    # 1С при создании инфобазы требует у роли права администратора БД,
    # поэтому роль копии создаём с superuser (пароль случайный, живёт до удаления копии)
    su -s /bin/bash postgres -c "psql -c \"set password_encryption='md5'; create role $ROLE login createdb superuser password '$PWD'\"" >/dev/null 2>&1 \
      || { echo "не удалось создать роль $ROLE"; exit 4; }
    su -s /bin/bash postgres -c "psql -c \"create database $NEW owner $ROLE\"" >/dev/null 2>&1 \
      || { echo "не удалось создать базу $NEW"; cleanup_failed "$NEW" "$ROLE"; exit 4; }

    echo "  [2/5] восстановление из дампа"
    ionice -c3 nice -n 10 su -s /bin/bash postgres -c "pg_restore -Fc -d $NEW '$DUMP'" >/tmp/sandbox-restore.log 2>&1
    RC=$?
    TABLES=$(tables_count "$NEW")
    ERRORS=$(grep -ci 'error:' /tmp/sandbox-restore.log 2>/dev/null || true)
    # pg_restore: 0 — без замечаний, 1 — предупреждения; всё выше или явные ошибки — провал
    if [ "${RC:-9}" -ge 2 ] || [ "${ERRORS:-0}" -gt 0 ]; then
      echo "        восстановление не удалось (код $RC, ошибок $ERRORS): $(grep -i 'error:' /tmp/sandbox-restore.log | head -1 | cut -c1-120)"
      cleanup_failed "$NEW" "$ROLE"
      exit 5
    fi
    echo "        таблиц в копии: ${TABLES:-0}, предупреждений: $(grep -ci 'warning' /tmp/sandbox-restore.log 2>/dev/null || echo 0)"
    # объекты после pg_restore принадлежат postgres: передаём их роли песочницы,
    # иначе 1С (роль без SUPERUSER) не сможет работать с базой
    su -s /bin/bash postgres -c "psql -d $NEW -c \"REASSIGN OWNED BY postgres TO $ROLE\"" >/dev/null 2>&1
    su -s /bin/bash postgres -c "psql -d $NEW -c \"GRANT ALL ON SCHEMA public TO $ROLE\"" >/dev/null 2>&1
    su -s /bin/bash postgres -c "psql -d $NEW -c \"ALTER DATABASE $NEW OWNER TO $ROLE\"" >/dev/null 2>&1
    echo "        права на объекты переданы роли $ROLE"

    # пользователи 1С берутся из текущей базы: в старых дампах их набор может не иметь прав
    HAS_SRC=$(su -s /bin/bash postgres -c "psql -d $SRC -Atc \"select count(*) from pg_tables where schemaname='public' and tablename='v8users'\"" 2>/dev/null)
    if [ "${HAS_SRC:-0}" = "1" ]; then
      su -s /bin/bash postgres -c "psql -d $SRC -c \"\\copy (select * from v8users) to '/tmp/sb-users.csv' csv\"" >/dev/null 2>&1
      if [ -s /tmp/sb-users.csv ]; then
        su -s /bin/bash postgres -c "psql -d $NEW -c \"delete from v8users\"" >/dev/null 2>&1
        su -s /bin/bash postgres -c "psql -d $NEW -c \"\\copy v8users from '/tmp/sb-users.csv' csv\"" >/dev/null 2>&1
        USERS=$(su -s /bin/bash postgres -c "psql -d $NEW -Atc \"select count(*) from v8users\"" 2>/dev/null)
        echo "        пользователей 1С из текущей базы: ${USERS:-0}"
      fi
      rm -f /tmp/sb-users.csv
    fi

    echo "  [3/5] информационная база в кластере"
    OUT=$($RAC "$RAS" infobase create --cluster="$CLUSTER" --name="$NEW" \
            --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$NEW" \
            --db-user="$ROLE" --db-pwd="$PWD" --locale=ru_RU \
            --scheduled-jobs-deny=on --license-distribution=allow "${AUTH[@]}" 2>&1)
    even=$?
    if [ $even -ne 0 ]; then
      echo "        не удалось создать инфобазу: $(echo "$OUT" | head -1)"
      cleanup_failed "$NEW" "$ROLE"
      exit 6
    fi

    echo "  [4/5] публикация"
    /usr/local/bin/1c-republish-base "$NEW" "$NEW" 2>&1 | sed 's/^/        /'

    echo "  [5/5] готово"
    ;;

  drop)
    NEW="${2:-}"
    [ -n "$NEW" ] || { echo "usage: 1c-sandbox drop <new>"; exit 64; }
    CLUSTER=$(cluster_get)
    ROLE="usr_${NEW//[^a-zA-Z0-9_]/_}"

    echo "  [1/4] завершаю сеансы"
    /usr/local/bin/1c-kick-sessions "$NEW" >/dev/null 2>&1 || true
    echo "  [2/4] удаляю инфобазу"
    UUID=$(infobase_uuid "$NEW")
    if [ -n "$UUID" ]; then
      $RAC "$RAS" infobase drop --cluster="$CLUSTER" --infobase="$UUID" "${AUTH[@]}" 2>&1 | sed 's/^/        /'
    else
      echo "        инфобаза не найдена — пропускаю"
    fi
    echo "  [3/4] удаляю базу и роль PostgreSQL"
    cleanup_failed "$NEW" "$ROLE"
    echo "  [4/4] снимаю публикацию"
    rm -rf "/var/www/1c/$NEW" 2>/dev/null
    rm -f "/etc/apache2/1c-publications/1c-${NEW}-web.conf" 2>/dev/null
    systemctl reload apache2 >/dev/null 2>&1 || true
    echo "удалено"
    ;;

  *)
    echo "usage: 1c-sandbox {create|drop|check} ..."; exit 64
    ;;
esac
