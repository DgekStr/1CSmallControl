#!/bin/bash
echo "=== env РєРѕРЅС‚РµР№РЅРµСЂР° wg-easy ==="
docker inspect wg-easy --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -Ei 'WG_HOST|WG_PORT|WG_PATH|WG_DEVICE|PORT' || echo "  РЅРµС‚ РїРµСЂРµРјРµРЅРЅС‹С… WG_*"

echo
echo "=== РіРґРµ РѕРїРёСЃР°РЅ РєРѕРЅС‚РµР№РЅРµСЂ (compose) ==="
for f in /opt/*/docker-compose*.yml /opt/*/compose*.yml /root/*.yml /root/wg-easy* /etc/systemd/system/*wg*; do
  [ -e "$f" ] && echo "  $f"
done
find / -maxdepth 4 -name 'docker-compose*.y*ml' 2>/dev/null | head -5 | sed 's/^/  /'

echo
echo "=== РїР°РЅРµР»СЊ FocusVPN ==="
systemctl list-units --type=service --no-pager 2>/dev/null | grep -Ei 'focus|panel|wg' | head -5 | sed 's/^/  /'
ls -1 /opt 2>/dev/null | sed 's/^/  /opt\//'
