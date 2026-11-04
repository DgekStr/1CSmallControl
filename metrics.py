"""Сбор метрик сервера для раздела «Статистика» (Linux, /proc)."""
import os
import shutil

_last_cpu = {'total': 0, 'idle': 0}


def _cpu_sample():
    with open('/proc/stat', 'r') as fh:
        parts = [int(x) for x in fh.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return sum(parts), idle


def _cpu_percent():
    total, idle = _cpu_sample()
    prev = _last_cpu
    pct = None
    if prev['total'] and total > prev['total']:
        dt = total - prev['total']
        di = idle - prev['idle']
        pct = max(0.0, min(100.0, (1.0 - di / dt) * 100.0))
    _last_cpu['total'], _last_cpu['idle'] = total, idle
    if pct is None:
        try:
            load = os.getloadavg()[0]
            pct = max(0.0, min(100.0, load / max(1, os.cpu_count()) * 100))
        except Exception:
            pct = 0.0
    return pct


def _meminfo():
    info = {}
    with open('/proc/meminfo', 'r') as fh:
        for line in fh:
            key, _, rest = line.partition(':')
            info[key] = int(rest.strip().split()[0]) * 1024
    total = info.get('MemTotal', 0)
    avail = info.get('MemAvailable', info.get('MemFree', 0))
    return total, max(0, total - avail)


def _net_totals():
    rx = tx = 0
    with open('/proc/net/dev', 'r') as fh:
        for line in fh.readlines()[2:]:
            name, _, data = line.partition(':')
            if name.strip() == 'lo':
                continue
            cols = data.split()
            rx += int(cols[0])
            tx += int(cols[8])
    return rx, tx


def _disks():
    """Реальные файловые системы: без tmpfs/proc и без дублей по устройству."""
    skip_prefix = ('/tmp', '/var/tmp', '/run', '/dev/shm', '/sys', '/proc', '/boot/efi')
    result, seen_dev, seen_mount = [], set(), set()
    with open('/proc/mounts', 'r') as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 2:
                continue
            dev, mount = parts[0], parts[1]
            if not dev.startswith('/dev/'):
                continue
            if mount in seen_mount or any(mount == p or mount.startswith(p + '/') for p in skip_prefix):
                continue
            if dev in seen_dev:
                continue
            seen_mount.add(mount)
            seen_dev.add(dev)
            try:
                usage = shutil.disk_usage(mount)
            except Exception:
                continue
            if usage.total <= 0:
                continue
            result.append({'mount': mount, 'used': usage.used, 'total': usage.total})
    result.sort(key=lambda d: d['total'], reverse=True)
    return result


def collect():
    cpu = _cpu_percent()
    mem_total, mem_used = _meminfo()
    rx, tx = _net_totals()
    disks = _disks()
    return {
        'cpu': round(cpu, 1),
        'cores': os.cpu_count() or 1,
        'ram_total': mem_total,
        'ram_used': mem_used,
        'net_rx': rx,
        'net_tx': tx,
        'disks': disks,
    }


def human_bytes(value):
    value = float(value or 0)
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if value < 1024 or unit == 'ТБ':
            return ('%d %s' % (value, unit)) if unit in ('Б', 'КБ') else ('%.1f %s' % (value, unit))
        value /= 1024.0
    return '%.1f ТБ' % value
