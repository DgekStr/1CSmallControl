#!/bin/bash
# Р’РєР»СЋС‡Р°РµС‚ HTTP/2 Рё keep-alive Рє РїРѕСЂС‚Р°Р»Сѓ РЅР° РїСЂРѕРєСЃРё 1c.dgek.ru
set -uo pipefail

CONF=/etc/nginx/conf.d/1c.dgek.ru.conf
BAK="/root/1c.dgek.ru.conf.bak.$(date +%Y%m%d%H%M%S)"
cp "$CONF" "$BAK"
echo "Р±СЌРєР°Рї: $BAK"

python3 - "$CONF" <<'PY'
import sys

path = sys.argv[1]
text = open(path, encoding='utf-8').read()

changed = []

# 1) HTTP/2 РЅР° HTTPS
if 'http2' not in text:
    text = text.replace("    listen 443 ssl;\n    listen [::]:443 ssl;\n",
                        "    listen 443 ssl;\n    listen [::]:443 ssl;\n    http2 on;\n", 1)
    changed.append('http2 on')

# 2) upstream СЃ keep-alive (СЃРµР№С‡Р°СЃ nginx РѕС‚РєСЂС‹РІР°РµС‚ РЅРѕРІРѕРµ СЃРѕРµРґРёРЅРµРЅРёРµ РЅР° РєР°Р¶РґС‹Р№ Р·Р°РїСЂРѕСЃ)
if 'upstream portal_1c' not in text:
    text = ("upstream portal_1c {\n"
            "    server 192.168.0.5:80;\n"
            "    keepalive 32;\n"
            "}\n\n") + text
    changed.append('upstream portal_1c keepalive 32')

text = text.replace("proxy_pass http://192.168.0.5;", "proxy_pass http://portal_1c;", 1)

# 3) РїСЂРѕРєСЃРёСЂРѕРІР°РЅРёРµ: Р±РµР· Р±СѓС„РµСЂРёР·Р°С†РёРё (РїРµС‡Р°С‚РЅС‹Рµ С„РѕСЂРјС‹ РёРґСѓС‚ РїРѕС‚РѕРєРѕРј), РґР»РёРЅРЅС‹Рµ poll РґРѕ 120 СЃ
if 'proxy_buffering' not in text:
    text = text.replace("        proxy_http_version 1.1;\n",
                        "        proxy_http_version 1.1;\n"
                        "        proxy_set_header Connection \"\";\n"
                        "        proxy_buffering off;\n"
                        "        proxy_read_timeout 120s;\n"
                        "        proxy_send_timeout 120s;\n", 1)
    changed.append('buffering off, timeouts 120s')

open(path, 'w', encoding='utf-8').write(text)
print('РёР·РјРµРЅРµРЅРѕ:', ', '.join(changed) if changed else 'РЅРёС‡РµРіРѕ (СѓР¶Рµ РЅР°СЃС‚СЂРѕРµРЅРѕ)')
PY

echo
echo "=== configtest ==="
nginx -t && nginx -s reload && echo "nginx РїРµСЂРµР·Р°РіСЂСѓР¶РµРЅ" || { echo "РћРЁРР‘РљРђ вЂ” РѕС‚РєР°С‚"; cp "$BAK" "$CONF"; nginx -t && nginx -s reload; }
