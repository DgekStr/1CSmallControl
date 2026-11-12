#!/bin/bash
. /etc/1c-portal/1c-session-admin.conf 2>/dev/null
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
C=$IC_CLUSTER
AU=(--cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD)
U=5c79c805-df18-437c-b3d0-e077c3c3d96a
timeout 20 $RAC 127.0.0.1:1545 infobase update --cluster=$C --infobase=$U --scheduled-jobs-deny=yes --sessions-deny=yes "${AU[@]}" >/dev/null 2>&1
echo "  режим запрета включён; чищу сеансы 5 минут"
for i in $(seq 1 150); do
  for s in $(timeout 8 $RAC 127.0.0.1:1545 session list --cluster=$C --infobase=$U "${AU[@]}" 2>/dev/null | grep -E '^session ' | awk '{print $3}'); do
    timeout 8 $RAC 127.0.0.1:1545 session terminate --cluster=$C --session=$s "${AU[@]}" >/dev/null 2>&1
  done
  sleep 2
done
echo "  очистка завершена"
