#!/bin/bash
echo "=== итоговая конфигурация (первые 30) ==="
pvesh get /cluster/backup --output-format json 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin)
on=[j for j in d if str(j.get("enabled")) in ("1","True","true")]
print("  заданий: %d, включено: %d" % (len(d), len(on)))
for j in sorted(d, key=lambda x: (x.get("schedule") or "")):
    print("   %-9s %-5s %-15s %-26s %s" % (j.get("schedule"), j.get("vmid"), j.get("storage"),
          j.get("prune-backups") or "-", "вкл" if str(j.get("enabled")) in ("1","True","true") else "ОТКЛ"))
'
echo "=== пробный бэкап VM 119 на локальный диск ==="
vzdump 119 --storage BK-PVE2-LOCAL --mode snapshot --compress zstd --prune-backups keep-last=5 --notes-template '{{guestname}}' 2>&1 | tail -8 | sed 's/^/  /'
