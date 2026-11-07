#!/bin/bash
echo "=== env РєРѕРЅС‚РµР№РЅРµСЂР° wg-easy ==="
docker inspect wg-easy --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | head -20

echo
echo "=== compose-С„Р°Р№Р»С‹ (Р±С‹СЃС‚СЂС‹Р№ РїРѕРёСЃРє) ==="
for d in /opt /root /srv /home /etc/wg-easy /var/lib/docker/volumes; do
  [ -d "$d" ] && find "$d" -maxdepth 3 -name 'compose*.y*ml' -o -maxdepth 3 -name 'docker-compose*.y*ml' 2>/dev/null | head -5
done | sed 's/^/  /'

echo
echo "=== СЋРЅРёС‚С‹ РїСЂРѕ vpn ==="
systemctl --no-pager list-units --type=service --all 2>/dev/null | grep -Ei 'focus|wg-easy|panel|wireguard' | head -8 | sed 's/^/  /'

echo
echo "=== РїР°РЅРµР»СЊ: РіРґРµ СЃР»СѓС€Р°РµС‚ ==="
ss -tlnp 2>/dev/null | grep -E ':9443|:51821' | sed 's/^/  /'
