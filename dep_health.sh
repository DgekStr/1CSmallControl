#!/bin/bash
set -uo pipefail
sed -i 's/\r$//' /tmp/1c-cluster-health.sh
install -o root -g root -m 755 /tmp/1c-cluster-health.sh /usr/local/bin/1c-cluster-health
bash -n /usr/local/bin/1c-cluster-health && echo "  синтаксис ok"
cat > /etc/systemd/system/1c-cluster-health.service <<'EOF'
[Unit]
Description=Проверка и авто-восстановление кластера 1С
[Service]
Type=oneshot
ExecStart=/usr/local/bin/1c-cluster-health
EOF
cat > /etc/systemd/system/1c-cluster-health.timer <<'EOF'
[Unit]
Description=Слежение за кластером 1С (каждые 2 минуты)
[Timer]
OnBootSec=90s
OnUnitActiveSec=120s
AccuracySec=10s
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now 1c-cluster-health.timer >/dev/null 2>&1
echo "  таймер: $(systemctl is-enabled 1c-cluster-health.timer) / $(systemctl is-active 1c-cluster-health.timer)"
echo "=== немедленный прогон ==="
/usr/local/bin/1c-cluster-health; echo "  код: $?"
tail -4 /var/log/1c-cluster-health.log 2>/dev/null | sed 's/^/  /'
for b in dgek-db test goncharov; do echo "  $b: $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8081/WEB/$b/)"; done
