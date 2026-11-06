"""Регламентные работы: окно работ, уведомления в веб-сессиях, отключение пользователей."""
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
    message TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    kicked_at TEXT,
    cancelled INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_MESSAGE = ('Сохраните данные и выйдите из 1С. После начала регламентных работ '
                   'несохранённые изменения будут потеряны.')


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    conn = db()
    try:
        conn.executescript(SCHEMA)
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


def window():
    """Ближайшее незакрытое окно работ."""
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM maintenance WHERE cancelled = 0 AND ends_at > ? "
            "ORDER BY starts_at LIMIT 1", (_now(),)).fetchone()
    finally:
        conn.close()
    return row


def state():
    """Состояние для интерфейса: none | planned | soon | active."""
    row = window()
    if not row:
        return {'phase': 'none'}
    now = time.time()
    start = _parse(row['starts_at'])
    end = _parse(row['ends_at'])
    if start is None or end is None:
        return {'phase': 'none'}
    if now >= end:
        phase = 'none'
    elif now >= start:
        phase = 'active'
    elif start - now <= 600:
        phase = 'soon'
    else:
        phase = 'planned'
    return {
        'phase': phase,
        'id': row['id'],
        'starts_at': row['starts_at'],
        'ends_at': row['ends_at'],
        'message': row['message'] or DEFAULT_MESSAGE,
        'comment': row['comment'] or '',
        'minutes_left': max(0, int((start - now) / 60)),
        'minutes_active': max(0, int((end - now) / 60)),
    }


def blocking():
    """Идут ли работы прямо сейчас (вход и работа запрещены)."""
    return state().get('phase') == 'active'


def create(starts_at, ends_at, message='', comment='', author=''):
    if not starts_at or not ends_at:
        return False, 'Укажите время начала и окончания'
    start, end = _parse(starts_at), _parse(ends_at)
    if start is None or end is None:
        return False, 'Неверный формат даты и времени'
    if end <= start:
        return False, 'Окончание должно быть позже начала'
    starts_at = starts_at.replace('T', ' ')[:16]
    ends_at = ends_at.replace('T', ' ')[:16]
    conn = db()
    try:
        conn.execute(
            "INSERT INTO maintenance(starts_at, ends_at, message, comment, created_by) "
            "VALUES(?,?,?,?,?)",
            (starts_at[:16], ends_at[:16], message or DEFAULT_MESSAGE, comment, author))
        conn.commit()
    finally:
        conn.close()
    return True, 'Регламентные работы запланированы'


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
    """Завершает сеансы 1С во всех опубликованных базах."""
    conn = db()
    try:
        bases = [r['slug'] for r in conn.execute("SELECT slug FROM bases WHERE is_active = 1")]
    finally:
        conn.close()
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


def mark_kicked(window_id):
    conn = db()
    try:
        conn.execute("UPDATE maintenance SET kicked_at = ? WHERE id = ?", (_now(), window_id))
        conn.commit()
    finally:
        conn.close()


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
    """Фоновой поток: отключение в начале работ и создание окон по расписанию."""
    st = state()
    row = window()
    if row and st.get('phase') == 'active' and not row['kicked_at']:
        kick_all()
        mark_kicked(row['id'])
        return 'kicked'

    auto = auto_settings()
    if not auto['enabled']:
        return None
    if row:  # уже есть запланированное окно
        return None

    try:
        weekday = int(auto['weekday'])
        hours, minutes = [int(x) for x in auto['time'].split(':')]
        duration = max(5, int(auto['minutes']))
    except (ValueError, TypeError):
        return None

    now = time.localtime()
    days_ahead = (weekday - now.tm_wday) % 7
    start = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hours, minutes, 0, 0, 0, -1))
    start += days_ahead * 86400
    if start <= time.time():
        start += 7 * 86400
    starts_at = time.strftime('%Y-%m-%d %H:%M', time.localtime(start))
    ends_at = time.strftime('%Y-%m-%d %H:%M', time.localtime(start + duration * 60))
    create(starts_at, ends_at, '', 'автоматическое окно по расписанию', 'расписание')
    return 'scheduled'
