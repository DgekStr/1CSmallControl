# Каталог архивов 1С для портала (песочницы)

Портал показывает клиенту список резервных копий и создаёт из них песочницы,
поэтому служба `1c-portal` (пользователь `www-data`) должна **читать**
каталог дампов на NAS.

## Как устроено

| Что | Значение |
|---|---|
| Шара | `//192.168.0.20/backup` (пользователь `dgek`) |
| Точка монтирования | `/mnt/1cbackup` |
| Каталог дампов | `/mnt/1cbackup/1csqlbase` (задаётся настройкой `backup_dir`) |
| Владелец/группа | `postgres:1cbackup`, режим `0770` (файлы `0660`) |

## Обязательные условия

1. Шара смонтирована (запись в `/etc/fstab`):

```
//192.168.0.20/backup /mnt/1cbackup cifs credentials=/etc/1c-backup/smb.cred,vers=3.0,iocharset=utf8,uid=999,gid=988,file_mode=0660,dir_mode=0770,nofail,_netdev,x-systemd.automount 0 0
```

2. `www-data` входит в группу `1cbackup`:

```
groupadd -r 1cbackup
usermod -aG 1cbackup www-data
usermod -aG 1cbackup postgres
```

3. Служба портала получает группу при старте (drop-in):

```
/etc/systemd/system/1c-portal.service.d/1cbackup.conf
[Service]
SupplementaryGroups=1cbackup
```

## Симптом, если условия не выполнены

В кабинете клиента при создании песочницы список копий **пуст**
(«Копий пока нет — дождитесь ночного архива»), при этом у администратора
список может быть виден (если его сессия попала в более новый worker).

В логе портала: `backup dir not readable: /mnt/1cbackup/1csqlbase`.

**Причина:** процессы gunicorn, запущенные до `usermod -aG`, не имеют
дополнительной группы — `glob` по каталогу с режимом `0770` возвращает пусто.
Лечится перезапуском службы: `systemctl restart 1c-portal`.

## Проверка

```
sudo -u www-data ls /mnt/1cbackup/1csqlbase/*.dump | wc -l      # > 0
PID=$(systemctl show -p MainPID --value 1c-portal); grep ^Groups /proc/$PID/status
curl -sk -b "<cookie клиента>" https://1c.dgek.ru/bases/9/copies
```
