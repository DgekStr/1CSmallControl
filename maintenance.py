"""Регламентные работы: окно работ, уведомления в веб-сессиях, отключение пользователей."""
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sqlite3
import subprocess
import time

DB_PATH = os.environ.get('PORTAL_DB', '/opt/1c-portal/portal.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    kick_at TEXT,
    message TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    kicked_at TEXT,
    finished_at TEXT,
    tune INTEGER NOT NULL DEFAULT 0,
    cancelled INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_MESSAGE = ('Срочные регламентные работы, закройте 1С. '
                   'После отключения несохранённые изменения будут потеряны.')
GRACE_MINUTES = 5

# хук Mattermost берётся из настроек портала (settings.json) или из окружения,
# в коде не хранится: репозиторий публичный
DEFAULT_HOOK = ''


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    conn = db()
    try:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(maintenance)")]
        for name, ddl in (
            ('kick_at', "ALTER TABLE maintenance ADD COLUMN kick_at TEXT"),
            ('finished_at', "ALTER TABLE maintenance ADD COLUMN finished_at TEXT"),
            ('tune', "ALTER TABLE maintenance ADD COLUMN tune INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _parse(value):
    text = (value or '').replace('T', ' ')[:16]
    try:
        return time.mktime(time.strptime(text, '%Y-%m-%d %H:%M'))
    except (ValueError, TypeError):
        return None


def _setting(name, default=''):
    try:
        conn = db()
        try:
            row = conn.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        finally:
            conn.close()
        return row['value'] if row and row['value'] else default
    except Exception:  # noqa: BLE001
        return default


def notify(text):
    hook = _setting('mm_hook', DEFAULT_HOOK)
    if not hook:
        return
    payload = json.dumps({'text': text}, ensure_ascii=False)
    try:
        subprocess.run(['curl', '-s', '-m', '10', '-X', 'POST', hook,
                        '-H', 'Content-Type: application/json; charset=utf-8',
                        '--data-binary', payload], capture_output=True, timeout=20)
    except Exception:  # noqa: BLE001
        pass


def window():
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM maintenance WHERE cancelled = 0 AND ends_at > ? "
            "ORDER BY starts_at LIMIT 1", (_now(),)).fetchone()
    finally:
        conn.close()
    return row


def state():
    """none | planned | soon | grace (идёт отсчёт) | active (сеансы отключены)."""
    row = window()
    if not row:
        return {'phase': 'none'}
    now = time.time()
    start = _parse(row['starts_at'])
    end = _parse(row['ends_at'])
    kick = _parse(row['kick_at']) if row['kick_at'] else None
    if start is None or end is None or now >= end:
        return {'phase': 'none'}
    if kick and start <= now < kick:
        phase = 'grace'
        seconds = int(kick - now)
    elif kick and now >= kick:
        phase = 'active'
        seconds = 0
    elif not kick and now >= start:
        phase = 'active'
        seconds = 0
    elif start - now <= 600:
        phase = 'soon'
        seconds = int(start - now)
    else:
        phase = 'planned'
        seconds = int(start - now)
    return {
        'phase': phase,
        'id': row['id'],
        'starts_at': row['starts_at'],
        'kick_at': row['kick_at'] or row['starts_at'],
        'ends_at': row['ends_at'],
        'message': row['message'] or DEFAULT_MESSAGE,
        'comment': row['comment'] or '',
        'minutes_left': max(0, int(seconds / 60)),
        'seconds_left': max(0, seconds),
        'minutes_active': max(0, int((end - now) / 60)),
    }


def blocking():
    return state().get('phase') == 'active'


def create(starts_at, ends_at, message='', comment='', author='', tune=0, kick_at=None):
    if not starts_at or not ends_at:
        return False, 'Укажите время начала и окончания', None
    start, end = _parse(starts_at), _parse(ends_at)
    if start is None or end is None:
        return False, 'Неверный формат даты и времени', None
    if end <= start:
        return False, 'Окончание должно быть позже начала', None
    starts_at = starts_at.replace('T', ' ')[:16]
    ends_at = ends_at.replace('T', ' ')[:16]
    kick_at = (kick_at or '').replace('T', ' ')[:16] or None
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO maintenance(starts_at, ends_at, kick_at, message, comment, created_by, tune) "
            "VALUES(?,?,?,?,?,?,?)",
            (starts_at, ends_at, kick_at, message or DEFAULT_MESSAGE, comment, author,
             1 if tune else 0))
        conn.commit()
        return True, 'Регламентные работы запланированы', cur.lastrowid
    finally:
        conn.close()


def cancel(maintenance_id=None):
    conn = db()
    try:
        if maintenance_id:
            conn.execute("UPDATE maintenance SET cancelled = 1 WHERE id = ?", (maintenance_id,))
        else:
            conn.execute("UPDATE maintenance SET cancelled = 1 WHERE cancelled = 0")
        conn.commit()
    finally:
        conn.close()
    return True, 'Регламентные работы отменены'


def kick_all():
    """Отключение сеансов 1С через серверный скрипт (rac)."""
    conn = db()
    try:
        bases = [r['slug'] for r in conn.execute("SELECT slug FROM bases WHERE is_active = 1")]
    finally:
        conn.close()
    if not bases:
        bases = []
    results = []
    for slug in bases:
        try:
            proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-kick-sessions', slug],
                                  capture_output=True, text=True, timeout=120)
            out = (proc.stdout or proc.stderr or '').strip().splitlines()
            results.append('%s: %s' % (slug, out[-1] if out else 'ok'))
        except Exception as exc:  # noqa: BLE001
            results.append('%s: ошибка %s' % (slug, exc))
    return results


def pg_mode(action, base=''):
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-pg-update-mode', action, base],
                              capture_output=True, text=True, timeout=600)
        out = (proc.stdout or proc.stderr or '').strip().splitlines()
        return out[-1] if out else ('код %s' % proc.returncode)
    except Exception as exc:  # noqa: BLE001
        return 'ошибка: %s' % exc


def mark_kicked(window_id):
    conn = db()
    try:
        conn.execute("UPDATE maintenance SET kicked_at = ? WHERE id = ?", (_now(), window_id))
        conn.commit()
    finally:
        conn.close()


def mark_finished(window_id):
    conn = db()
    try:
        conn.execute("UPDATE maintenance SET finished_at = ? WHERE id = ?", (_now(), window_id))
        conn.commit()
    finally:
        conn.close()


def start_now(minutes=30, comment='', author='', tune=False, message='', grace=GRACE_MINUTES):
    """«Запустить работы сейчас»: отсчёт grace минут, затем отключение, конец через minutes."""
    try:
        minutes = max(grace + 5, int(minutes))
    except (TypeError, ValueError):
        minutes = 30
    now = time.time()
    starts = time.strftime('%Y-%m-%d %H:%M', time.localtime(now))
    kick = time.strftime('%Y-%m-%d %H:%M', time.localtime(now + grace * 60))
    ends = time.strftime('%Y-%m-%d %H:%M', time.localtime(now + minutes * 60))
    cancel()
    ok, msg, window_id = create(starts, ends, message, comment, author,
                                tune=1 if tune else 0, kick_at=kick)
    if not ok:
        return False, msg
    tune_note = ''
    if tune:
        pg_mode('on')
        tune_note = ', ускорение PostgreSQL включено'
    notify('**1C: срочные регламентные работы** — старт %s, отключение через %d мин, '
           'окончание %s%s. %s' % (starts, grace, ends, tune_note, comment or ''))
    return True, 'Работы начаты: отключение через %d мин, окончание %s' % (grace, ends)


def stop_now(reason='вручную'):
    row = window()
    tune = bool(row['tune']) if row else False
    cancel()
    if row:
        mark_finished(row['id'])
    note = ''
    if tune:
        note = pg_mode('off')
    notify('**1C: регламентные работы** — завершены (%s).%s' % (reason, (' ' + note) if note else ''))
    return True, 'Работы завершены'


def auto_settings():
    conn = db()
    try:
        values = {r['name']: r['value'] for r in conn.execute(
            "SELECT name, value FROM settings WHERE name LIKE 'maint_auto%'")}
    finally:
        conn.close()
    return {
        'enabled': values.get('maint_auto') == '1',
        'weekday': values.get('maint_auto_weekday', '5'),
        'time': values.get('maint_auto_time', '03:00'),
        'minutes': values.get('maint_auto_minutes', '60'),
    }


def tick():
    """Отключение по отсчёту, завершение работ и создание окон по расписанию."""
    now = time.time()
    row = window()
    if row:
        kick = _parse(row['kick_at']) if row['kick_at'] else _parse(row['starts_at'])
        end = _parse(row['ends_at'])
        if kick and end and kick <= now < end and not row['kicked_at']:
            kick_all()
            mark_kicked(row['id'])
            notify('**1C: регламентные работы** — сеансы отключены, вход закрыт до %s.'
                   % row['ends_at'])
            return 'kicked'

    conn = db()
    try:
        done = conn.execute(
            "SELECT * FROM maintenance WHERE cancelled = 0 AND finished_at IS NULL "
            "AND ends_at <= ? ORDER BY ends_at DESC LIMIT 5", (_now(),)).fetchall()
    finally:
        conn.close()
    for item in done:
        if item['tune']:
            pg_mode('off')
        mark_finished(item['id'])
        notify('**1C: регламентные работы** — завершены. Вход в базы открыт.')

    auto = auto_settings()
    if not auto['enabled'] or window():
        return None

    try:
        weekday = int(auto['weekday'])
        hours, minutes = [int(x) for x in auto['time'].split(':')]
        duration = max(5, int(auto['minutes']))
    except (ValueError, TypeError):
        return None

    local = time.localtime()
    days_ahead = (weekday - local.tm_wday) % 7
    start = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, hours, minutes, 0, 0, 0, -1))
    start += days_ahead * 86400
    if start <= time.time():
        start += 7 * 86400
    starts_at = time.strftime('%Y-%m-%d %H:%M', time.localtime(start))
    ends_at = time.strftime('%Y-%m-%d %H:%M', time.localtime(start + duration * 60))
    create(starts_at, ends_at, '', 'автоматическое окно по расписанию', 'расписание')
    return 'scheduled'
