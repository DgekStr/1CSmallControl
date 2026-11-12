# Технический журнал действий — 12.11.2026

Все операции выполнялись на сервере `dgek@192.168.0.5` (ключ `id_ed25519_dgek1c`,
sudo через пароль), прокси-хост nginx `192.168.0.15`, гипервизор `pve2` `192.168.0.18`.
Секреты в журнале заменены плейсхолдерами `<...>`.

---

## A. Кластер 1С

### Конфигурация
```
1С:Предприятие 8.3.27.2342
кластер: maincluster, UUID c5c7b09d-83be-45a5-b6c2-dbfdeb7e3470, порт 1541
RAS: 127.0.0.1:1545
каталог реестра: /home/usr1cv8/.1cv8/1C/1cv8/reg_1541
```

### Инфобазы (итоговые)
| Инфобаза | UUID | БД PostgreSQL | Публикация |
|---|---|---|---|
| test | 5c79c805-… | test | /WEB/test/ |
| dgek_db | 5e60a96c-… | dgekdb | /WEB/dgek_db/ |
| goncharov2026 | 088376ce-… | goncharov2026 | /WEB/goncharov2026/ |
| montes-bp | 67f77cbb-… | montes-bp | /WEB/montes-bp/ |
| montes_buh | b4de8491-… | montes_buh | нет |
| goncharov (фантом) | 37472d16-… | удалена | нет |

### Диагностические команды (использовались многократно)
```bash
. /etc/1c-portal/1c-session-admin.conf
RAC=/opt/1cv8/x86_64/8.3.27.2342/rac
$RAC 127.0.0.1:1545 infobase summary list --cluster=$IC_CLUSTER \
     --cluster-user=$IC_CLUSTER_USER --cluster-pwd=$IC_CLUSTER_PWD
$RAC 127.0.0.1:1545 session list --cluster=$IC_CLUSTER --infobase=<uuid> ...
$RAC 127.0.0.1:1545 infobase update --cluster=$IC_CLUSTER --infobase=<uuid> \
     --sessions-deny=yes --scheduled-jobs-deny=yes ...
```

### Инцидент «503 после ребута»
```
состояние: ragent=1 rmngr=0 1541=закрыт
действие: systemctl restart srv1cv8; systemctl restart ras.service
результат: rmngr=1, 1541=открыт, базы 200
```

### Инцидент «no working process»
```
текст: Could not find an available working process… Attempts: 5, interval: 1000 ms
причина: rphost стартует позже кластера; healthcheck перезапустил службу повторно
```

### Рассинхрон пароля роли БД (goncharov, test, goncharov2026)
```
лог PostgreSQL: «Пароль не подходит для пользователя usr_<db>»
лечение: clear alerts; ALTER ROLE usr_<db> PASSWORD '<new>';
         rac infobase update --db-user=usr_<db> --db-pwd='<new>'
проверка: PGPASSWORD=<new> psql -h 127.0.0.1 -U usr_<db> -d <db> -Atc 'select 1' → 1
```

### Удаление базы `goncharov`
```
DROP DATABASE goncharov (force)
rm -rf /var/www/1c/goncharov
delete from bases / access в portal.db
rm -rf reg_1541/{37472d16,9f9511f4,7ce767a0}
rac infobase drop → «Недостаточно прав пользователя на информационную базу goncharov»
попытка правки реестра → откат из /root/1CV8Clst*.lst.bak.2043, кластер жив
итог: фантомная запись осталась
```

---

## B. Портал

### Развёртывание изменений
```bash
scp app.py templates/... dgek@192.168.0.5:/tmp/
sed -i 's/\r$//' /tmp/app.py
install -o root -g www-data -m 640 /tmp/app.py /opt/1c-portal/app.py
systemctl restart 1c-portal
```

### Версия
```
2.0.8 → 2.0.9 (очистка cookie, кнопка ♻️) → 2.1.0 (релиз)
PORTAL_VERSION в /etc/systemd/system/1c-portal.service
```

### Добавленные маршруты/функции
| Что | Где |
|---|---|
| `/sessions/kick-mine` (фоновое задание) | app.py |
| очистка cookie в `/logout` | app.py |
| размеры баз по `db_name` | `_base_sizes_fetch` |
| резолв базы `slug|ib_name|db_name` | `web_gate` |
| `.v8i` по `ib_name` | `base_v8i` |
| публикация по URL + `ib_name` | `base_republish` |
| оверлей «Система запускается…» | `web_denied.html`, `portal.css` |
| логотип 1С в карточках | `portal.html`, `portal.css`, `static/1c-logo.png` |
| эталонные пользователи | `1c-create-base` → `1c-apply-template-users` |

### Сервисные скрипты на сервере
| Скрипт | Назначение |
|---|---|
| `/usr/local/bin/1c-cluster-health` | проверка 1541, rmngr, RAC, rphost; перезапуск после 2 сбоев |
| `/usr/local/bin/1c-heal-bases` | синхронизация паролей БД: сначала проверка, сброс только сломанных |
| `/usr/local/bin/1c-verify-base` | сброс пароля роли + `rac update` + проверка под ключ |
| `/usr/local/bin/1c-kick-sessions` | завершение сеансов базы (резолв по `summary list`) |
| `/usr/local/bin/1c-kick-user` | завершение сеансов пользователя во всех базах |
| `/usr/local/bin/1c-republish-base` | публикация `<имя> <Ref>` |
| `/usr/local/bin/1c-apply-template-users` | эталонные пользователи в базу |
| `/usr/local/bin/1c-monitor` | мониторинг, `monitor-status.json` |
| `/usr/local/bin/1c-night-clean` | ночная чистка 1С |
| `/usr/local/bin/1c-backup.sh` | бэкапы `pg_dump` на NAS |

### Права sudo (www-data, NOPASSWD)
```
1c-monitor, 1c-night-clean, 1c-kick-user, 1c-kick-sessions, 1c-republish-base
```

### Портал: ключевые проверки
```bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/WEB/<base>/
curl -sk -o /dev/null -w '%{http_code}' https://1c.dgek.ru/WEB/<base>/
```

---

## C. Инфраструктура

### Диск 1С-сервера
```
до:   /dev/sda2 49G, занято 42G, свободно 4,5G (91%)
было: расширение ВМ +10G
growpart /dev/sda 2; resize2fs /dev/sda2
после: 59G, занято 43G, свободно 14G (76%)
```

### pve2 (192.168.0.18)
```
swap до: 8G (занято 7,6G)
swapoff -a; lvextend -L 16G /dev/pve/swap; mkswap; swapon -a
swap после: 16G (занято 0)
```

### Мониторинг бэкапов
```
check_backup() → свежесть /mnt/1cbackup/*.dump (порог 28 ч)
алерты бэкап-спама прекращены
```

### Полнотекстовая индексация
```
рост: 321 файл / 10 мин; каталоги 1Cv8FTxt по 2,2–2,6 ГБ (~8,7 ГБ)
нагрузка: rphost 78% CPU, load 5,6 → после завершения load 0,85, прирост 0 МБ/мин
```

---

## D. Git / релиз

```
16 локальных коммитов → 1 релизный (squash)
git reset --soft origin/main; git commit
удалено из индекса: soft/ (649 МБ + 3,1 ГБ дистрибутивы), добавлено в .gitignore
санация: <CLUSTER_PASSWORD>, <MM_HOOK_URL> в 6 файлах
коммит: 91be9d6 «release 2.1.0: …»
тег: v2.1.0 (annotated, force после amend)
push: fa585f4..91be9d6 main → main; * [new tag] v2.1.0
```

После релиза накопились локальные коммиты (healthcheck-фикс, самовосстановление паролей,
md-промпт, безопасный heal) — **в git не отправлены**.

---

## E. Проверки «здоровья» на момент закрытия

```
srv1cv8: active   ras: active   1c-portal: active   apache2: active
ragent=1 rmngr=1 rphost=1 ras=1
1540=2 1541=2 8080=1 8081=1
RAM: 3,1 Gi / 29 Gi (доступно 26 Gi)
диск /: 40G / 59G (17G свободно)
страницы: test 200, dgek-db 200, goncharov2026 200, montes-bp 200
извне: healthz 200, login 200, /WEB/* → 302 (требуется вход)
heal-bases: ok 4, ошибок 0, «проверено без сброса»
```
