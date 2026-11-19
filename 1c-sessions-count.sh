#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# РЎРѕСЃС‚РѕСЏРЅРёРµ СЃРµР°РЅСЃРѕРІ Рё Р±Р»РѕРєРёСЂРѕРІРєРё СЂРµРіР»Р°РјРµРЅС‚РЅС‹С… Р·Р°РґР°РЅРёР№ РїРѕ Р±Р°Р·Р°Рј.
# РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: 1c-sessions-count <РёРјСЏ_Р±Р°Р·С‹> [РёРјСЏ_Р±Р°Р·С‹...]
# Р’С‹РІРѕРґ: В«<РёРјСЏ> <СЃРµР°РЅСЃРѕРІ> <jobs:on|off>В», РїРѕ СЃС‚СЂРѕРєРµ РЅР° Р±Р°Р·Сѓ.
# `infobase info` РѕРїСЂР°С€РёРІР°РµС‚СЃСЏ РїР°СЂР°Р»Р»РµР»СЊРЅРѕ: 4 Р±Р°Р·С‹ в‰€ 1 СЃ РІРјРµСЃС‚Рѕ 4 СЃ.
set -uo pipefail

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CA=(--cluster-user="${IC_CLUSTER_USER:-}" --cluster-pwd="${IC_CLUSTER_PWD:-}")
# РґР»СЏ infobase info РЅСѓР¶РµРЅ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃР°РјРѕР№ РР‘
IBA=(--infobase-user="${IC_ADMIN_USER:-}" --infobase-pwd="${IC_ADMIN_PWD:-}")

if [ $# -lt 1 ]; then
  echo "usage: 1c-sessions-count <name> [name...]"
  exit 64
fi

CLUSTER=${IC_CLUSTER:-$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')}
[ -n "$CLUSTER" ] || exit 2

# РєР°СЂС‚Р° РёРјСЏ РёРЅС„РѕР±Р°Р·С‹ в†’ uuid
MAP=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null \
      | awk -F' *: *' '/^infobase /{u=$2} /^name /{if (u!="") {print $2"|"u; u=""}}')

# РѕРґРёРЅ СЂР°Р· Р·Р°Р±РёСЂР°РµРј СЃРїРёСЃРѕРє СЃРµР°РЅСЃРѕРІ
SESS=$($RAC "$RAS" session list --cluster="$CLUSTER" "${CA[@]}" 2>/dev/null)

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT

# 1) РёРјСЏ в†’ uuid
: > "$TMP/names"
for NAME in "$@"; do
  U=$(printf '%s\n' "$MAP" | awk -F'|' -v n="$NAME" '$1==n {print $2; exit}')
  printf '%s|%s\n' "$NAME" "$U" >> "$TMP/names"
done

# 2) Р±Р»РѕРєРёСЂРѕРІРєР° Р·Р°РґР°РЅРёР№ (jobs) вЂ” РїР°СЂР°Р»Р»РµР»СЊРЅРѕ РїРѕ РІСЃРµРј Р±Р°Р·Р°Рј
while IFS='|' read -r NAME U; do
  [ -n "$U" ] || continue
  (
    $RAC "$RAS" infobase info --cluster="$CLUSTER" --infobase="$U" "${CA[@]}" "${IBA[@]}" 2>/dev/null \
      | awk -F' *: *' '/^scheduled-jobs-deny/{print $2; exit}' > "$TMP/jobs.$U"
  ) &
done < "$TMP/names"
wait

# 3) СЃС‡С‘С‚С‡РёРєРё СЃРµР°РЅСЃРѕРІ вЂ” РѕРґРёРЅ РїСЂРѕС…РѕРґ РїРѕ СЃРїРёСЃРєСѓ, РїРѕ uuid РёРЅС„РѕР±Р°Р·С‹
printf '%s\n' "$SESS" | awk -F' *: *' '
  /^session /{s=$2}
  /^infobase /{i=$2}
  /^app-id /{a=$2}
  /^user-name /{u=$2}
  /^$/{
    if (s != "" && i != "" && a != "BackgroundJob" && u != "DefUser") c[i]++
    s=""; i=""; a=""; u=""
  }
  END{
    if (s != "" && i != "" && a != "BackgroundJob" && u != "DefUser") c[i]++
    for (k in c) print k"|"c[k]
  }' > "$TMP/counts"

# 4) РІС‹РІРѕРґ РІ РёСЃС…РѕРґРЅРѕРј РїРѕСЂСЏРґРєРµ
while IFS='|' read -r NAME U; do
  if [ -z "$U" ]; then
    echo "$NAME 0 off"
    continue
  fi
  N=$(awk -F'|' -v u="$U" '$1==u {print $2; exit}' "$TMP/counts")
  J=$(cat "$TMP/jobs.$U" 2>/dev/null)
  [ -n "$J" ] || J="off"
  echo "$NAME ${N:-0} $J"
done < "$TMP/names"
