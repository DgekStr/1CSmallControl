#!/bin/bash
# РЎРѕР·РґР°С‘С‚ РїСѓСЃС‚СѓСЋ СЃРµСЂРІРµСЂРЅСѓСЋ Р±Р°Р·Сѓ 1РЎ: СЂРѕР»СЊ Рё Р±Р°Р·Р° PostgreSQL, РёРЅС„РѕСЂРјР°С†РёРѕРЅРЅР°СЏ Р±Р°Р·Р°
# РІ РєР»Р°СЃС‚РµСЂРµ, РїСѓР±Р»РёРєР°С†РёСЏ РґР»СЏ РїРѕСЂС‚Р°Р»Р°. Р”Р°РЅРЅС‹Рµ Р·Р°РіСЂСѓР¶Р°СЋС‚СЃСЏ РїРѕР·Р¶Рµ РёР· .dt С‡РµСЂРµР· РљРѕРЅС„РёРіСѓСЂР°С‚РѕСЂ.
# РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: 1c-create-base <РєРѕРґ_Р±Р°Р·С‹> [РёРјСЏ_Р±Р°Р·С‹_РІ_Р‘Р”]
set -uo pipefail

NAME="${1:-}"
DB="${2:-$NAME}"
[ -n "$NAME" ] || { echo "usage: 1c-create-base <slug> [db_name]"; exit 64; }

CONF=/etc/1c-portal/1c-session-admin.conf
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

RAC=${IC_RAC:-/opt/1cv8/x86_64/8.3.27.2342/rac}
RAS=${IC_RAS:-127.0.0.1:1545}
CLUSTER=$($RAC "$RAS" cluster list 2>/dev/null | awk '/^cluster/{print $3; exit}')
[ -n "$CLUSTER" ] || { echo "РєР»Р°СЃС‚РµСЂ 1РЎ РЅРµРґРѕСЃС‚СѓРїРµРЅ"; exit 2; }

# СѓР¶Рµ РµСЃС‚СЊ РІ РєР»Р°СЃС‚РµСЂРµ?
EXISTS=$($RAC "$RAS" infobase summary list --cluster="$CLUSTER" 2>/dev/null | grep -c "name     : $NAME")
if [ "$EXISTS" -gt 0 ]; then
  echo "Р±Р°Р·Р° $NAME СѓР¶Рµ РµСЃС‚СЊ РІ РєР»Р°СЃС‚РµСЂРµ"
  /usr/local/bin/1c-republish-base "$NAME" "$DB" >/dev/null 2>&1 || true
  echo "РїСѓР±Р»РёРєР°С†РёСЏ РѕР±РЅРѕРІР»РµРЅР°"
  exit 0
fi

ROLE="usr_${DB//[^a-zA-Z0-9_]/_}"
PWD=$(openssl rand -hex 12)

echo "  [1/3] СЂРѕР»СЊ PostgreSQL $ROLE"
# 1РЎ СЃРѕР·РґР°С‘С‚ C-С„СѓРЅРєС†РёРё, РїРѕСЌС‚РѕРјСѓ СЂРѕР»СЊ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ СЃСѓРїРµСЂРїРѕР»СЊР·РѕРІР°С‚РµР»РµРј (С€С‚Р°Р±РЅР°СЏ РїСЂР°РєС‚РёРєР° 1РЎ)
# pg_hba РёСЃРїРѕР»СЊР·СѓРµС‚ md5 вЂ” РїР°СЂРѕР»СЊ СЂРѕР»Рё С‚РѕР¶Рµ РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РІ md5
su -s /bin/bash postgres -c "psql -Atc \"select 1 from pg_roles where rolname='$ROLE'\"" 2>/dev/null | grep -q 1 && \
  su -s /bin/bash postgres -c "psql -c \"set password_encryption='md5'; alter role $ROLE login createdb superuser password '$PWD'\"" >/dev/null 2>&1 || \
  su -s /bin/bash postgres -c "psql -c \"set password_encryption='md5'; create role $ROLE login createdb superuser password '$PWD'\"" >/dev/null 2>&1 || \
  { echo "РЅРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ СЂРѕР»СЊ"; exit 3; }

echo "  [2/3] РёРЅС„РѕСЂРјР°С†РёРѕРЅРЅР°СЏ Р±Р°Р·Р° РІ РєР»Р°СЃС‚РµСЂРµ"
OUT=$($RAC "$RAS" infobase create --cluster="$CLUSTER" --name="$NAME" \
        --dbms=PostgreSQL --db-server=127.0.0.1 --db-name="$DB" \
        --db-user="$ROLE" --db-pwd="$PWD" --locale=ru_RU --create-database \
        --license-distribution=allow 2>&1)
if echo "$OUT" | grep -qiE 'error|РѕС€РёР±'; then
  echo "РЅРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ Р±Р°Р·Сѓ: $(echo "$OUT" | head -2 | tr '\n' ' ')"
  exit 4
fi

echo "  [3/3] РїСѓР±Р»РёРєР°С†РёСЏ"
/usr/local/bin/1c-republish-base "$NAME" "$DB" | sed 's/^/    /'

echo "РіРѕС‚РѕРІР° РїСѓСЃС‚Р°СЏ Р±Р°Р·Р° $NAME вЂ” Р·Р°РіСЂСѓР·РёС‚Рµ РґР°РЅРЅС‹Рµ С‡РµСЂРµР· РљРѕРЅС„РёРіСѓСЂР°С‚РѕСЂ (.dt)"
