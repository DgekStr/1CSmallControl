# Диск ssd1 на pve2 (Netac SSD 240GB) и перенос 1С

## Диск

| Параметр | Значение |
|---|---|
| Модель | Netac SSD 240GB |
| Серийный номер | AA20221107240G195119 |
| Прошивка | U0510A0 |
| Интерфейс | SATA 3.2 (на pve2 порт SATA II — 3.0 Гбит/с) |
| Наработка | 144 ч |
| Износ (Wear_Leveling) | 0 |
| Переназначенные сектора | 0 |
| Ошибки CRC/ECC | 0 |
| Температура | 24 °C |
| TRIM | поддерживается, passdown включён |
| SMART | PASSED |

Потребительский SSD без DRAM и без PLP. Для 1С приемлемо при наличии UPS и
ночных бэкапов на CIFS (`//192.168.0.20/backup/1csqlbase`).

## Хранилище

| Параметр | Значение |
|---|---|
| ID | `ssd1` (только узел pve2) |
| Тип | LVM-thin, VG `ssd1`, pool `data` |
| Размер | 223,35 ГиБ |
| После переноса ВМ 213 | занято 33 % (77 ГБ), свободно 149 ГиБ |

## Скорости

| Тест | Результат |
|---|---|
| 4k dsync, сырой диск | 1292 / 1376 IOPS |
| 4k dsync, LVM-thin (LV 2 ГБ) | 423 / 419 IOPS |
| 4k dsync, внутри ВМ 213 | **264 / 274 / 292 IOPS** |
| Последовательная запись | 228 МБ/с (сырой) · 165 (thin) · **106 (в ВМ)** |
| Чтение | 248 МБ/с |

До переноса (ZFS `www-ssd`, Samsung 860 EVO): 96–100 IOPS и 41 МБ/с в ВМ.
Прирост примерно **в 3 раза по IOPS и в 2,5 раза по записи**.

## Перенос ВМ 213

```
qm shutdown 213
qm move-disk 213 scsi0 ssd1 --delete 0   # 9 мин 52 с, 60 ГБ
qm move-disk 213 scsi1 ssd1 --delete 0   # 7 мин 03 с, 40 ГБ
qm set 213 --scsi0 ssd1:vm-213-disk-0,cache=none,iothread=1,ssd=1,discard=on
qm set 213 --scsi1 ssd1:vm-213-disk-1,cache=none,iothread=1,ssd=1,discard=on
qm start 213
```

Старые диски оставлены как `unused0` / `unused1` на `www-ssd` — точка возврата.
Удалить их (освободит ~100 ГБ в пуле `www-ssd`) после недели стабильной работы:

```
qm disk rescan --vmid 213          # проверить, что не нужны
qm set 213 --delete unused0
qm set 213 --delete unused1
```
