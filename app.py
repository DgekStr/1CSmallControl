"""Портал доступа к базам 1С: клиентский вход + админка."""
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import hmac
import http.client
import base64
import json
import urllib.request
from urllib.parse import quote
import os
import re
import sqlite3
import struct
import secrets
import subprocess
import threading
import time

import maintenance
import metrics
from functools import wraps

from werkzeug.middleware.proxy_fix import ProxyFix
from flask import (has_request_context, Flask, g, redirect, render_template, request, session, stream_with_context,
                   url_for, abort, flash, Response, make_response, send_from_directory)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('PORTAL_DB', os.path.join(BASE_DIR, 'portal.db'))

# Имя сервера 1С, которое показывается клиентам в инструкции по Конфигуратору.
IC_HOST = os.environ.get('PORTAL_IC_HOST', '1c.example.ru')
# Контакты сопровождения (блок «Нужна помощь с платформой?»).
SUPPORT_URL = os.environ.get('PORTAL_SUPPORT_URL', 'https://example.ru/contacts.html')
SUPPORT_NAME = os.environ.get('PORTAL_SUPPORT_NAME', 'example.ru')
# Версия портала — выводится в шапке и подвале.
APP_VERSION = os.environ.get('PORTAL_VERSION', '2.0.3')

app = Flask(__name__)
# S-09: ограничение размера запроса
app.config.setdefault('MAX_CONTENT_LENGTH', 8 * 1024 * 1024)
# за nginx: реальный IP клиента и схема https
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 2592000  # 30 дней, ссылки версионируются
_secret_file = os.path.join(BASE_DIR, '.secret_key')
if os.path.exists(_secret_file):
    app.secret_key = open(_secret_file, 'rb').read()
else:
    app.secret_key = secrets.token_bytes(32)
    with open(_secret_file, 'wb') as fh:
        fh.write(app.secret_key)
    os.chmod(_secret_file, 0o600)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,  # портал всегда за HTTPS-прокси
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    organization TEXT NOT NULL DEFAULT '',
    pass_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'client',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    organization TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    url_path TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100
);
CREATE TABLE IF NOT EXISTS access (
    user_id INTEGER NOT NULL,
    base_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, base_id)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ended_at TEXT,
    ip TEXT NOT NULL DEFAULT '',
    ua TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS client_sessions (
    sid TEXT PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    app TEXT NOT NULL DEFAULT '',
    host TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    cpu REAL NOT NULL DEFAULT 0,
    rx INTEGER NOT NULL DEFAULT 0,
    tx INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def db():
    if 'db' not in g:
        # C-06: WAL и таймаут ожидания — меньше блокировок при параллельной записи
        g.db = sqlite3.connect(DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA synchronous=NORMAL')
        g.db.execute('PRAGMA busy_timeout=5000')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db



@app.after_request
def _security_headers(resp):
    """S-11: базовые защитные заголовки (CSP не ставим на веб-клиент 1С)."""
    if request.path.startswith('/WEB/'):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    headers_csp = ("default-src 'self'; img-src 'self' data:; "
                   "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                   "connect-src 'self'; frame-ancestors 'self'")
    resp.headers.setdefault('Content-Security-Policy', headers_csp)
    return resp




@app.before_request
def _must_change_guard():
    """Новый клиент обязан сменить пароль при первом входе (пункт 3)."""
    uid = session.get('uid')
    if not uid:
        return None
    if request.endpoint in ('settings_password', 'logout', 'static', 'theme', 'asset'):
        return None
    row = db().execute("SELECT must_change_password FROM users WHERE id = ?", (uid,)).fetchone()
    if row and row['must_change_password']:
        flash('Смените пароль — это обязательно при первом входе')
        return redirect(url_for('settings_password'))


@app.before_request
def _check_session_fp():
    """S-11: если пароль сменили или учётку заблокировали — сессия недействительна."""
    uid = session.get('uid')
    if not uid:
        return None
    try:
        row = db().execute("SELECT pass_hash, is_active FROM users WHERE id = ?", (uid,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        session.clear()
        return redirect(url_for('login'))
    fp = _session_fp(row)
    if not session.get('fp'):
        session['fp'] = fp
        return None
    if session['fp'] != fp:
        session.clear()
        audit('session_revoked', 'uid %s' % uid)
        return redirect(url_for('login'))


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


QR_TTL = 120  # секунды жизни QR-кода


def init_db():
    # несколько воркеров стартуют одновременно: ждём блокировку, а не падаем
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA busy_timeout=30000')
    for attempt in range(5):
        try:
            conn.executescript(SCHEMA)
            break
        except sqlite3.OperationalError:
            if attempt == 4:
                raise
            time.sleep(1)
    for table in ('users', 'bases'):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]
        if 'organization' not in cols:
            conn.execute("ALTER TABLE %s ADD COLUMN organization TEXT NOT NULL DEFAULT ''" % table)
    base_cols = [r[1] for r in conn.execute("PRAGMA table_info(bases)")]
    if 'update_mode' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN update_mode TEXT")
    if 'db_name' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN db_name TEXT")
    if 'cluster_state' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN cluster_state TEXT")
    if 'auto_user' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN auto_user TEXT")
    if 'auto_pwd' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN auto_pwd TEXT")
    if 'is_sandbox' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN is_sandbox INTEGER DEFAULT 0")
    if 'sandbox_of' not in base_cols:
        conn.execute("ALTER TABLE bases ADD COLUMN sandbox_of TEXT")

    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if 'must_change_password' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if 'vpn_enabled' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN vpn_enabled INTEGER DEFAULT 0")
    if 'vpn_config' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN vpn_config TEXT")
    if 'totp_secret' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
    if 'totp_enabled' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0")
    if 'totp_backup' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN totp_backup TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS login_fails (
        username TEXT NOT NULL,
        ip TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        blocked_until REAL,
        notified INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (username, ip))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS qr_logins (
        token TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        ip TEXT,
        ua TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        uid INTEGER,
        used INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT NOT NULL,
        kind TEXT NOT NULL,
        title TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        log_path TEXT,
        user_id INTEGER,
        ref TEXT,
        created_at TEXT,
        finished_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sandboxes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        base_id INTEGER,
        source_slug TEXT NOT NULL,
        source_db TEXT NOT NULL,
        slug TEXT NOT NULL,
        dump_path TEXT NOT NULL,
        dump_date TEXT,
        keep_days INTEGER NOT NULL DEFAULT 3,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'creating',
        error TEXT,
        size TEXT)""")
    conn.execute("UPDATE bases SET db_name = slug WHERE db_name IS NULL OR db_name = ''")
    conn.commit()
    maintenance.init()
    for idx in (
        "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts)",
        "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit(action)",
        "CREATE INDEX IF NOT EXISTS idx_visits_user ON visits(username)",
        "CREATE INDEX IF NOT EXISTS idx_visits_started ON visits(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)",
        "CREATE INDEX IF NOT EXISTS idx_clients_last ON client_sessions(last_seen)",
    ):
        try:
            conn.execute(idx)
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("DELETE FROM metrics WHERE id NOT IN (SELECT id FROM metrics ORDER BY id DESC LIMIT 500)")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)")
    if not conn.execute("SELECT 1 FROM migrations WHERE name = 'localtime_v1'").fetchone():
        for sql in (
            "UPDATE visits SET started_at = datetime(started_at, '+3 hours'), "
            "last_seen = datetime(last_seen, '+3 hours'), ended_at = datetime(ended_at, '+3 hours') "
            "WHERE ended_at IS NOT NULL",
            "UPDATE visits SET started_at = datetime(started_at, '+3 hours'), "
            "last_seen = datetime(last_seen, '+3 hours') WHERE ended_at IS NULL",
            "UPDATE audit SET ts = datetime(ts, '+3 hours')",
            "UPDATE metrics SET ts = datetime(ts, '+3 hours')",
            "UPDATE client_sessions SET first_seen = datetime(first_seen, '+3 hours'), "
            "last_seen = datetime(last_seen, '+3 hours')",
        ):
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.execute("INSERT INTO migrations(name) VALUES('localtime_v1')")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        admin_pwd = os.environ.get('PORTAL_ADMIN_PASSWORD')
        if not admin_pwd:
            admin_pwd = secrets.token_urlsafe(12)
            print('=' * 64)
            print('  PORTAL_ADMIN_PASSWORD не задан — сгенерирован пароль:')
            print('  admin / %s' % admin_pwd)
            print('  Сохраните его и смените при первом входе.')
            print('=' * 64)
        conn.execute(
            "INSERT INTO users(username, full_name, pass_hash, role) VALUES(?,?,?,?)",
            ('admin', 'Администратор', generate_password_hash(admin_pwd), 'admin'))
        if os.environ.get('PORTAL_SEED_DEMO') == '1':
            demo_pwd = os.environ.get('PORTAL_DEMO_PASSWORD') or secrets.token_urlsafe(9)
            for login, name in [('demo1', 'Демо-клиент 1'), ('demo2', 'Демо-клиент 2')]:
                conn.execute(
                    "INSERT INTO users(username, full_name, pass_hash, role) VALUES(?,?,?,?)",
                    (login, name, generate_password_hash(demo_pwd), 'client'))
            conn.execute("INSERT INTO bases(slug,title,description,url_path,sort_order) VALUES(?,?,?,?,?)",
                         ('demo', 'Демо-база', 'Информационная база 1С', '/WEB/demo/', 10))
            for uid in [r[0] for r in conn.execute("SELECT id FROM users WHERE role='client'")]:
                for bid in [r[0] for r in conn.execute("SELECT id FROM bases")]:
                    conn.execute("INSERT OR IGNORE INTO access(user_id, base_id) VALUES(?,?)", (uid, bid))
    conn.commit()
    conn.close()


def audit(action, details=''):
    """Запись в журнал не должна блокировать запрос: отдельное соединение, таймаут 2 с."""
    try:
        actor = session.get('user', 'anonymous') if has_request_context() else 'system'
        conn = sqlite3.connect(DB_PATH, timeout=2)
        try:
            conn.execute("INSERT INTO audit(actor, action, details) VALUES(?,?,?)", (actor, action, details))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


TRUSTED_PROXIES = {'127.0.0.1', '::1', '192.168.0.15', '192.168.0.5'}


def _client_ip():
    """Реальный IP клиента. X-Forwarded-For принимаем только от своих прокси (S-01)."""
    peer = request.remote_addr or ''
    if peer in TRUSTED_PROXIES:
        fwd = request.headers.get('X-Forwarded-For', '')
        if fwd:
            return fwd.split(',')[0].strip()
    return peer


@app.before_request
def _touch_visit():
    """Отмечает активность текущего визита не чаще раза в минуту."""
    vid = session.get('visit')
    if not vid:
        return
    now = int(time.time())
    if now - int(session.get('seen') or 0) < 60:
        return
    session['seen'] = now
    try:
        db().execute("UPDATE visits SET last_seen = datetime('now','localtime') WHERE id = ? AND ended_at IS NULL",
                     (vid,))
        db().commit()
    except Exception:
        pass


def csrf_token():
    tok = session.get('csrf')
    if not tok:
        tok = secrets.token_urlsafe(32)
        session['csrf'] = tok
    return tok


app.jinja_env.globals['csrf_token'] = csrf_token
app.jinja_env.globals['ic_host'] = IC_HOST
app.jinja_env.globals['support_url'] = SUPPORT_URL
app.jinja_env.globals['support_name'] = SUPPORT_NAME
app.jinja_env.globals['app_version'] = APP_VERSION


def check_csrf():
    tok = session.get('csrf')
    if not tok or request.form.get('csrf') != tok:
        abort(400, 'CSRF token mismatch')



def _safe_next(value, default='/'):
    """S-07: разрешаем только локальные пути для редиректа после входа."""
    from urllib.parse import urlsplit
    if not value:
        return default
    if '\\' in value or value.startswith('//'):
        return default
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return default
    return value if value.startswith('/') else default



def _session_fp(row):
    """S-11: отпечаток пользователя, привязанный к паролю и активности."""
    import hashlib
    raw = '%s|%s' % (row['pass_hash'] or '', 1 if row['is_active'] else 0)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]




# ===== настройки клиента: пароль, 2FA, доверенные устройства =====


def _partial():
    """Запрос из модального окна: отвечаем JSON, без перехода на страницу."""
    return request.headers.get('X-Partial') == '1'


def _password_ok(pw):
    """Минимум 8 символов, есть буквы и цифры."""
    if not pw or len(pw) < 8:
        return False
    return any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)


def _trusted_set(resp, uid):
    token = secrets.token_urlsafe(32)
    h = hashlib.sha256(token.encode()).hexdigest()
    days = int(_setting_get('trusted_days') or 30)
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    exp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + days * 86400))
    conn = db()
    conn.execute("INSERT INTO trusted_devices (user_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
                 (uid, h, now, exp))
    conn.commit()
    resp.set_cookie('portal_td', token, max_age=days * 86400, httponly=True, samesite='Lax',
                    secure=request.is_secure)
    return resp


def _trusted_user():
    token = request.cookies.get('portal_td')
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    row = db().execute("SELECT * FROM trusted_devices WHERE token_hash = ?", (h,)).fetchone()
    if not row:
        return None
    if row['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        conn = db()
        conn.execute("DELETE FROM trusted_devices WHERE id = ?", (row['id'],))
        conn.commit()
        return None
    return db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (row['user_id'],)).fetchone()


def _trusted_drop(user_id=None):
    conn = db()
    if user_id is None:
        conn.execute("DELETE FROM trusted_devices")
    else:
        conn.execute("DELETE FROM trusted_devices WHERE user_id = ?", (user_id,))
    conn.commit()


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('uid'):
            return redirect(url_for('login', next=request.path))
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('uid'):
            return redirect(url_for('login', next=request.path))
        if session.get('role') != 'admin':
            abort(403)
        return fn(*a, **kw)
    return wrapper


@app.template_filter('dt_ru')
def _dt_ru(value):
    """2026-11-18 02:34:10 → 18.11.2026 02:34 (общероссийский вид)."""
    text = str(value or '').strip()
    if len(text) >= 16 and text[4] == '-' and text[7] == '-':
        return '%s.%s.%s %s' % (text[8:10], text[5:7], text[0:4], text[11:16])
    return text


@app.route('/')
def index():
    if not session.get('uid'):
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin'))
    rows = db().execute("""
        SELECT b.* FROM bases b
        JOIN access a ON a.base_id = b.id
        WHERE a.user_id = ? AND b.is_active = 1 AND COALESCE(b.is_sandbox, 0) = 0
        ORDER BY b.sort_order, b.title""", (session['uid'],)).fetchall()
    jobs = {}
    if rows:
        slugs = tuple(b['slug'] for b in rows)
        # счётчики сеансов через rac могут отвечать секундами — не блокируем страницу
        info = _cached_swr('counts:' + ','.join(slugs), 60, 3600,
                           lambda: _session_counts(list(slugs)), wait=False) or {}
        jobs = {k: v.get('jobs', 'off') for k, v in info.items()}
    pg_mode = _pg_mode_state()
    sizes = _base_sizes(rows) if rows else {}
    urow = db().execute("SELECT vpn_enabled, vpn_config FROM users WHERE id = ?",
                        (session['uid'],)).fetchone()
    vpn_ready = bool(urow and urow['vpn_enabled'] and urow['vpn_config'])
    sandboxes = _sandbox_active(session['uid'])
    sandbox_links = {}
    for sb in sandboxes:
        if sb['status'] == 'ready':
            b = db().execute("SELECT id FROM bases WHERE slug = ?", (sb['slug'],)).fetchone()
            if b:
                sandbox_links[sb['id']] = b['id']
    return render_template('portal.html', vpn_ready=vpn_ready, bases=rows, jobs=jobs, pg_mode=pg_mode,
                           sizes=sizes, maint=maintenance.state(),
                           sandboxes=sandboxes, sandbox_links=sandbox_links,
                           sandbox_enabled=_setting_get('sandbox_enabled') == '1',
                           sandbox_keep=int(_setting_get('sandbox_keep_days') or 3),
                           ic_server=_setting_get('ic_server_name') or 'srv.1c.dgek.ru')


# ---------------- шлюз к публикациям 1С ----------------
# Наружу /WEB/ отдаётся только через портал: Apache проксирует запросы сюда,
# портал проверяет сессию и право на базу, и лишь затем сам обращается к 1cws
# на внутреннем порту (127.0.0.1:8081), который снаружи недоступен.
BACKEND_HOST = os.environ.get('PORTAL_1C_BACKEND_HOST', '127.0.0.1')
BACKEND_PORT = int(os.environ.get('PORTAL_1C_BACKEND_PORT', '8081'))
HOP_BY_HOP = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host',
}
WEB_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']


@app.route('/WEB/<slug>', methods=['GET', 'HEAD'])
@login_required
def web_gate_redirect(slug):
    qs = request.query_string.decode('latin-1')
    return redirect('/WEB/%s/%s' % (slug, ('?' + qs) if qs else ''))



WEB_DENIED = {
    'no-access': dict(
        kind_label='ДОСТУП ЗАКРЫТ',
        title='Доступ к базе закрыт',
        icon='lock',
        message='Эта база больше не доступна вашей учётной записи.',
        hint='Администратор портала мог отключить доступ. Попросите его выдать доступ заново '
             'в разделе «Доступы» — после этого база снова появится в кабинете.',
    ),
    'not-found': dict(
        kind_label='БАЗА НЕ НАЙДЕНА',
        title='Такой базы нет',
        icon='database-zap',
        message='База не найдена или скрыта администратором.',
        hint='Проверьте адрес: возможно, базу переименовали или удалили. '
             'Актуальный список — в кабинете портала.',
    ),
    'upstream': dict(
        kind_label='СЕРВЕР 1С НЕ ОТВЕЧАЕТ',
        title='База временно недоступна',
        icon='plug-zap',
        message='Сервер 1С не отвечает или выполняется обслуживание базы.',
        hint='Подождите минуту и обновите страницу. Если не помогает — сообщите администратору.',
    ),
}


def _web_denied(slug, kind='no-access', status=403):
    info = dict(WEB_DENIED.get(kind) or WEB_DENIED['no-access'])
    html = render_template('web_denied.html', slug=slug, **info)
    resp = make_response(html, status)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/WEB/<slug>/', defaults={'rest': ''}, methods=WEB_METHODS)
@app.route('/WEB/<slug>/<path:rest>', methods=WEB_METHODS)
@login_required
def web_gate(slug, rest=''):
    # S-08: нормализуем путь и не выпускаем за пределы своей публикации
    import posixpath
    segs = (rest or '').split('/')
    bad = ('\\' in (rest or '') or '/' in slug
           or any(seg in ('.', '..') for seg in segs)
           or any(ord(ch) < 32 for ch in (rest or '')))
    if bad:
        audit('web_traversal', '%s / %s' % (slug, rest))
        return _web_denied(slug, 'not-found', 404)
    safe_rest = posixpath.normpath('/WEB/%s/%s' % (slug, rest or ''))[len('/WEB/'):]
    if not safe_rest.startswith(slug):
        audit('web_traversal', '%s / %s' % (slug, rest))
        return _web_denied(slug, 'not-found', 404)
    base = db().execute("SELECT * FROM bases WHERE slug = ? AND is_active = 1", (slug,)).fetchone()
    if not base:
        return _web_denied(slug, 'not-found', 404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], base['id'])).fetchone()
        if not allowed:
            audit('web_denied', slug)
            return _web_denied(slug, 'no-access', 403)

    if session.get('role') != 'admin' and maintenance.blocking():
        return redirect(url_for('maintenance_page'))
    path = '/WEB/%s/%s' % (slug, rest)
    if request.query_string:
        path += '?' + request.query_string.decode('latin-1')

    body = None
    if request.method not in ('GET', 'HEAD'):
        body = request.get_data()

    # на стартовую страницу веб-клиента добавляем плашку регламентных работ,
    # поэтому запрашиваем её без сжатия (остальные ресурсы идут как есть)
    inject_banner = request.method == 'GET' and rest == ''
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in HOP_BY_HOP and k.lower() != 'content-length'}
    if inject_banner:
        headers = {k: v for k, v in headers.items() if k.lower() != 'accept-encoding'}

    try:
        conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=300)
        conn.request(request.method, path, body=body, headers=headers)
        resp = conn.getresponse()

        # печатные формы 1С отдаёт постепенно — передаём потоком, иначе браузер
        # видит пустое окно, пока не придёт весь документ
        if not inject_banner and request.method != 'HEAD':
            def stream(conn=conn, resp=resp):
                try:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass

            out = Response(stream_with_context(stream()), status=resp.status, content_type=None)
            out.headers.pop('Content-Type', None)
            for key, value in resp.getheaders():
                if key.lower() not in HOP_BY_HOP and key.lower() != 'content-length':
                    out.headers.add(key, value)
            out.headers['X-Accel-Buffering'] = 'no'
            return out

        data = resp.read()
        # content_type=None — чтобы не подмешивать Content-Type Flask'а к ответу 1С
        if inject_banner and b'<html' in data[:2048].lower():
            try:
                text = data.decode('utf-8', 'ignore')
                snippet = '<script src="/static/maint.js" defer></script>'
                if '</body>' in text:
                    text = text.replace('</body>', snippet + '</body>', 1)
                else:
                    text = text + snippet
                data = text.encode('utf-8')
            except Exception:  # noqa: BLE001
                pass
        out = Response(data, status=resp.status, content_type=None)
        out.headers.pop('Content-Type', None)
        for key, value in resp.getheaders():
            if key.lower() not in HOP_BY_HOP and key.lower() != 'content-length':
                out.headers.add(key, value)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        audit('web_error', '%s: %s' % (slug, exc))
        return _web_denied(slug, 'upstream', 502)
    return out



LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 15 * 60          # окно подсчёта, секунд
LOGIN_BLOCK = 15 * 60           # время блокировки, секунд
def _mm_notify(text, hook=None):
    """Сообщение в Mattermost. Хук берётся из настроек портала (или из env)."""
    url = hook
    if not url:
        try:
            url = (_settings_all().get('mm_hook') or '').strip()
        except Exception:  # noqa: BLE001
            url = ''
    if not url:
        url = os.environ.get('PORTAL_MM_LOGIN_HOOK', '')
    if not url:
        return False
    try:
        payload = json.dumps({'text': text}, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=payload,
                                     headers={'Content-Type': 'application/json; charset=utf-8'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            resp.read()
        return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001
        return False


def _login_blocked(username, ip):
    """Возвращает остаток блокировки в секундах (0 — не заблокирован)."""
    row = db().execute("SELECT * FROM login_fails WHERE username = ? AND ip = ?",
                       (username, ip)).fetchone()
    if not row or not row['blocked_until']:
        return 0
    left = int(row['blocked_until'] - time.time())
    return left if left > 0 else 0


def _login_fail(username, ip):
    """Считает неудачные попытки; на пятой блокирует и пишет в Mattermost."""
    conn = db()
    row = conn.execute("SELECT * FROM login_fails WHERE username = ? AND ip = ?",
                       (username, ip)).fetchone()
    now = time.time()
    if row:
        count = (row['count'] or 0) + 1
        conn.execute("UPDATE login_fails SET count = ?, blocked_until = ? WHERE username = ? AND ip = ?",
                     (count, row['blocked_until'], username, ip))
    else:
        count = 1
        conn.execute("INSERT INTO login_fails(username, ip, count) VALUES(?,?,?)", (username, ip, count))

    if count >= LOGIN_MAX_FAILS:
        conn.execute("UPDATE login_fails SET blocked_until = ?, notified = 0 WHERE username = ? AND ip = ?",
                     (now + LOGIN_BLOCK, username, ip))
        conn.commit()
        if (_settings_all().get('mm_login_alerts') or '1') == '1':
            _mm_notify('#### 🚫 Портал 1С: блокировка входа\n\n'
                   'Пользователь **%s** с IP **%s** — %d неудачных попыток.\n'
                       'Вход заблокирован на %d минут.' % (username, ip, count, LOGIN_BLOCK // 60))
        conn.execute("UPDATE login_fails SET notified = 1 WHERE username = ? AND ip = ?", (username, ip))
    conn.commit()


def _login_ok(username, ip):
    db().execute("DELETE FROM login_fails WHERE username = ? AND ip = ?", (username, ip))
    db().commit()



# ===== вход администратора по QR-коду =====

def _qr_png_data_uri(text):
    """PNG с QR-кодом в виде data:URI (генерируется локально, без внешних сервисов)."""
    try:
        proc = subprocess.run(['qrencode', '-t', 'PNG', '-s', '7', '-m', '2', '-o', '-', text],
                              capture_output=True, timeout=10)
        if proc.returncode == 0 and proc.stdout:
            return 'data:image/png;base64,' + base64.b64encode(proc.stdout).decode('ascii')
    except Exception:  # noqa: BLE001
        pass
    return ''


def _qr_purge(conn):
    """Удаляет просроченные и использованные одноразовые ссылки."""
    cutoff = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time() - 3600))
    conn.execute("DELETE FROM qr_logins WHERE created_at < ?", (cutoff,))


@app.route('/login/qr')
def qr_login_page():
    """Экран ожидания: показывает QR, который подтверждают с телефона."""
    if session.get('uid'):
        return redirect('/')

    conn = db()
    _qr_purge(conn)
    token = secrets.token_urlsafe(24)
    now = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    conn.execute("INSERT INTO qr_logins (token, created_at, ip, ua, status) VALUES (?,?,?,?, 'pending')",
                 (token, now, _client_ip(), (request.headers.get('User-Agent') or '')[:180]))
    conn.commit()

    link = request.host_url.rstrip('/') + '/qr/' + token
    audit('qr_start', _client_ip())
    return render_template('qr.html', token=token, qr=_qr_png_data_uri(link),
                           link=link, ttl=QR_TTL)


@app.route('/qr/status')
def qr_status():
    """Опрос состояния: как только телефон подтвердил — пускаем в админку."""
    token = request.args.get('token') or ''
    conn = db()
    row = conn.execute("SELECT * FROM qr_logins WHERE token = ?", (token,)).fetchone()
    if not row:
        return {'status': 'unknown'}
    created = time.mktime(time.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')) - time.timezone
    if row['status'] == 'pending' and time.time() - created > QR_TTL:
        conn.execute("UPDATE qr_logins SET status = 'expired' WHERE token = ?", (token,))
        conn.commit()
        return {'status': 'expired'}
    if row['status'] == 'approved' and not row['used'] and row['uid']:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (row['uid'],)).fetchone()
        conn.execute("UPDATE qr_logins SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        if user and user['is_active']:
            session.clear()
            session['uid'] = user['id']
            session['user'] = user['username']
            session['name'] = user['full_name'] or user['username']
            session['role'] = user['role']
            session.permanent = True
            _login_ok(user['username'], _client_ip())
            audit('qr_login', user['username'])
            return {'status': 'ok', 'next': '/admin' if user['role'] == 'admin' else '/'}
        return {'status': 'error'}
    return {'status': row['status']}


@app.route('/qr/<token>', methods=['GET', 'POST'])
def qr_confirm(token):
    """Страница на телефоне: подтвердить вход администратора."""
    conn = db()
    row = conn.execute("SELECT * FROM qr_logins WHERE token = ?", (token,)).fetchone()
    if not row:
        abort(404)
    if row['status'] == 'expired' or row['used']:
        abort(410)

    if request.method == 'POST':
        check_csrf()
        if not session.get('uid'):
            flash('Чтобы подтвердить вход, сначала войдите в портал на этом устройстве')
            return redirect(url_for('login', next=request.path))
        conn.execute("UPDATE qr_logins SET status = 'approved', uid = ? WHERE token = ?",
                     (session['uid'], token))
        conn.commit()
        audit('qr_approve', '%s %s' % (session['user'], row['ip']))
        return render_template('qr_confirm.html', done=True, ip=row['ip'], ua=row['ua'])

    return render_template('qr_confirm.html', done=False, token=token, ip=row['ip'],
                           ua=row['ua'], logged=bool(session.get('uid')),
                           who=session.get('name') or session.get('user') or '')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and maintenance.blocking() and request.args.get('admin') != '1':
        return render_template('maintenance.html', st=maintenance.state())
    error = None
    if request.method == 'POST':
        check_csrf()
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        ip = _client_ip()
        left = _login_blocked(username, ip)
        if left:
            error = 'Слишком много неудачных попыток. Вход заблокирован ещё на %d мин.' % (left // 60 + 1)
            audit('login_blocked', '%s %s' % (username, ip))
            return render_template('login.html', trusted=_trusted_user(), error=error)
        row = db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and row['is_active'] and check_password_hash(row['pass_hash'], password):
            if row['totp_enabled'] and row['totp_secret']:
                session.clear()
                session['pending_uid'] = row['id']
                session['pending_at'] = int(time.time())
                session['pending_next'] = _safe_next(request.args.get('next'))
                audit('login_2fa_required', row['username'])
                return render_template('two_factor.html', error=None)
            session.clear()
            session['uid'] = row['id']
            session['user'] = row['username']
            session['name'] = row['full_name'] or row['username']
            session['role'] = row['role']
            session.permanent = True
            cur = db().execute(
                "INSERT INTO visits(username, ip, ua) VALUES(?,?,?)",
                (row['username'], _client_ip(),
                 (request.headers.get('User-Agent') or '')[:200]))
            db().commit()
            session['visit'] = cur.lastrowid
            session['seen'] = int(time.time())
            _login_ok(row['username'], ip)
            audit('login', _client_ip())
            nxt = _safe_next(request.args.get('next'))
            return redirect(nxt if nxt.startswith('/') else '/')
        error = 'Неверный логин или пароль'
        _login_fail(username, ip)
        audit('login_failed', '%s %s' % (username, ip))
    return render_template('login.html', error=error)


@app.route('/settings/password', methods=['GET', 'POST'])
@login_required
def settings_password():
    uid = session['uid']
    error = None
    if request.method == 'POST':
        check_csrf()
        cur = request.form.get('current') or ''
        new = request.form.get('new') or ''
        rep = request.form.get('repeat') or ''
        row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not check_password_hash(row['pass_hash'], cur):
            error = 'Текущий пароль указан неверно'
        elif new != rep:
            error = 'Новый пароль и повтор не совпадают'
        elif not _password_ok(new):
            error = 'Новый пароль: минимум 8 символов, буквы и цифры'
        elif check_password_hash(row['pass_hash'], new):
            error = 'Новый пароль совпадает с текущим'
        else:
            conn = db()
            conn.execute("UPDATE users SET pass_hash = ?, must_change_password = 0 WHERE id = ?",
                         (generate_password_hash(new), uid))
            conn.commit()
            _trusted_drop(uid)
            fresh = conn.execute("SELECT pass_hash, is_active FROM users WHERE id = ?", (uid,)).fetchone()
            session['fp'] = _session_fp(fresh)
            audit('password_changed', 'самостоятельно')
            if _partial():
                return {'ok': True, 'message': 'Пароль изменён. Остальные устройства потребуют вход заново.'}
            flash('Пароль изменён. Остальные устройства потребуют вход заново.')
            return redirect('/')
    if _partial():
        return {'ok': False, 'error': error} if request.method == 'POST' else {'ok': True}
    must = db().execute("SELECT must_change_password FROM users WHERE id = ?", (uid,)).fetchone()
    return render_template('settings_password.html', error=error,
                           must=bool(must and must['must_change_password']))


@app.route('/settings/2fa', methods=['GET'])
@login_required
def settings_2fa():
    uid = session['uid']
    row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row['totp_secret']:
        secret = _totp_new_secret()
        conn = db()
        conn.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, uid))
        conn.commit()
    else:
        secret = row['totp_secret']
    uri = _totp_uri(secret, row['username'], request.host.split(':')[0])
    qr = ''
    try:
        proc = subprocess.run(['qrencode', '-t', 'PNG', '-s', '7', '-m', '2', '-o', '-', uri],
                              capture_output=True, timeout=10)
        if proc.returncode == 0 and proc.stdout:
            qr = 'data:image/png;base64,' + base64.b64encode(proc.stdout).decode('ascii')
    except Exception:  # noqa: BLE001
        qr = ''
    backup = json.loads(row['totp_backup'] or '[]')
    if _partial():
        return {'ok': True, 'enabled': bool(row['totp_enabled']), 'secret': secret,
                'qr': qr, 'backup_left': len(backup)}
    return render_template('settings_2fa.html', enabled=bool(row['totp_enabled']),
                           secret=secret, qr=qr, backup_left=len(backup))


@app.route('/settings/2fa/enable', methods=['POST'])
@login_required
def settings_2fa_enable():
    check_csrf()
    uid = session['uid']
    row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    code = (request.form.get('code') or '').strip()
    if not row['totp_secret'] or not _totp_verify(row['totp_secret'], code):
        if _partial():
            return {'ok': False, 'error': 'Код не подошёл. Проверьте время на телефоне.'}
        flash('Код не подошёл. Проверьте время на телефоне.')
        return redirect(url_for('settings_2fa'))
    codes, hashed = _backup_codes_new()
    conn = db()
    conn.execute("UPDATE users SET totp_enabled = 1, totp_backup = ? WHERE id = ?", (hashed, uid))
    conn.commit()
    audit('2fa_enabled', 'клиент включил сам')
    if _partial():
        return {'ok': True, 'enabled': True, 'codes': codes,
                'message': 'Двухфакторный вход включён. Сохраните коды восстановления.'}
    return render_template('settings_2fa.html', enabled=True, secret=row['totp_secret'],
                           qr=None, backup_left=len(codes), codes=codes)


@app.route('/settings/2fa/disable', methods=['POST'])
@login_required
def settings_2fa_disable():
    check_csrf()
    uid = session['uid']
    row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    code = (request.form.get('code') or '').strip()
    pwd = request.form.get('password') or ''
    ok = bool(code and row['totp_secret'] and _totp_verify(row['totp_secret'], code))
    if not ok and pwd:
        ok = check_password_hash(row['pass_hash'], pwd)
    if not ok:
        if _partial():
            return {'ok': False, 'error': 'Укажите код из приложения или пароль портала'}
        flash('Укажите код из приложения или пароль портала')
        return redirect(url_for('settings_2fa'))
    conn = db()
    conn.execute("UPDATE users SET totp_enabled = 0, totp_backup = NULL WHERE id = ?", (uid,))
    conn.commit()
    _trusted_drop(uid)
    audit('2fa_disabled', 'клиент отключил сам')
    if _partial():
        return {'ok': True, 'enabled': False, 'message': 'Двухфакторный вход отключён'}
    flash('Двухфакторный вход отключён')
    return redirect(url_for('settings_2fa'))


@app.route('/trusted/login', methods=['POST'])
def trusted_login():
    """Вход по коду с запомненного устройства, без пароля."""
    check_csrf()
    user = _trusted_user()
    if not user or not user['totp_enabled']:
        flash('Это устройство больше не доверенное — войдите с паролем')
        return redirect(url_for('login'))
    code = (request.form.get('code') or '').strip()
    ok = _totp_verify(user['totp_secret'], code)
    if not ok:
        ok, _rest = _backup_code_check(user['totp_backup'], code)
    if not ok:
        audit('trusted_login_failed', user['username'])
        flash('Неверный код')
        return redirect(url_for('login'))
    return _finish_login(user)


@app.route('/logout', methods=['POST'])
def logout():
    audit('logout', session.get('user', ''))
    if session.get('visit'):
        db().execute("UPDATE visits SET ended_at = datetime('now','localtime') WHERE id = ? AND ended_at IS NULL",
                     (session['visit'],))
        db().commit()
    session.clear()
    return redirect(url_for('login'))




def _open_url(base):
    """Ссылка на веб-клиент базы; при автовходе добавляет пользователя 1С."""
    url = '/WEB/%s/' % base['slug']
    user = (base['auto_user'] or '').strip() if 'auto_user' in base.keys() else ''
    if user:
        pwd = base['auto_pwd'] or ''
        url += '?N=%s&P=%s' % (quote(user, safe=''), quote(pwd, safe=''))
    return url


@app.route('/open/<slug>')
@login_required
def open_base(slug):
    row = db().execute("SELECT * FROM bases WHERE slug = ? AND is_active = 1", (slug,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], row['id'])).fetchone()
        if not allowed:
            abort(403)
    audit('open_base', slug)
    url = row['url_path'] or ('/WEB/%s/' % row['slug'])
    user = (row['auto_user'] or '').strip() if 'auto_user' in row.keys() else ''
    if user and '?' not in url:
        url += '?N=%s&P=%s' % (quote(user, safe=''), quote(row['auto_pwd'] or '', safe=''))
    return redirect(url)


# ---------------- админка ----------------

def _session_counts(slugs):
    """Сколько активных сеансов 1С у каждой базы (через rac)."""
    if not slugs:
        return {}
    try:
        proc = subprocess.run(
            ['sudo', '-n', '/usr/local/bin/1c-sessions-count'] + list(slugs),
            capture_output=True, text=True, timeout=40)
        counts = {}
        for line in (proc.stdout or '').splitlines():
            parts = line.split()
            if len(parts) >= 2:
                counts[parts[0]] = {
                    'n': int(parts[1]) if parts[1].isdigit() else 0,
                    'jobs': parts[2] if len(parts) > 2 else 'off',
                }
        return counts
    except Exception:  # noqa: BLE001
        return {}


_cache = {}


def _cached(key, ttl, fn):
    """Простое кэширование тяжёлых вызовов (rac) с временем жизни."""
    force = request.args.get('refresh') == '1'
    now = time.time()
    hit = _cache.get(key)
    if hit and not force and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def _cached_swr(key, ttl, max_age, fn, wait=True):
    """Отдаёт кэш сразу, а если он устарел — обновляет в фоне (страница не ждёт rac)."""
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    if hit and now - hit[0] < max_age:
        def refresh():
            try:
                _cache[key] = (time.time(), fn())
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=refresh, daemon=True).start()
        return hit[1]
    if not wait:
        def load():
            try:
                _cache[key] = (time.time(), fn())
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=load, daemon=True).start()
        return {}
    value = fn()
    _cache[key] = (now, value)
    return value


def _cache_stamp(key):
    hit = _cache.get(key)
    return time.strftime('%H:%M:%S', time.localtime(hit[0])) if hit else time.strftime('%H:%M:%S')


def _licenses():
    """Занято/всего клиентских лицензий 1С (ключи HASP + активные сеансы)."""
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-licenses'],
                              capture_output=True, text=True, timeout=30)
        parts = (proc.stdout or '').split()
        if len(parts) >= 4:
            return {'used': int(parts[0]), 'total': int(parts[1]),
                    'net': int(parts[2]), 'local': int(parts[3])}
    except Exception:  # noqa: BLE001
        pass
    return {'used': 0, 'total': 0, 'net': 0, 'local': 0}


def _warm_once():
    """Обновляет кэш тяжёлых вызовов в фоне, чтобы страницы открывались мгновенно."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        slugs = tuple(r['slug'] for r in conn.execute("SELECT slug FROM bases WHERE is_active = 1"))
    finally:
        conn.close()
    if slugs:
        _cache['counts:' + ','.join(slugs)] = (time.time(), _session_counts(list(slugs)))
    _cache['live'] = (time.time(), _sessions_snapshot())


def _start_warmer():
    def loop():
        while True:
            try:
                _warm_once()
            except Exception:  # noqa: BLE001
                pass
            try:
                maintenance.tick()
            except Exception:  # noqa: BLE001
                pass
            try:
                warm_counts()
            except Exception:  # noqa: BLE001
                pass
            try:
                warm_sizes()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(45)

    threading.Thread(target=loop, daemon=True).start()


@app.route('/admin')
@admin_required
def admin():
    users = db().execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    bases = db().execute("SELECT * FROM bases WHERE COALESCE(is_sandbox, 0) = 0 "
                         "ORDER BY sort_order, title").fetchall()
    links = {(r['user_id'], r['base_id']) for r in db().execute("SELECT * FROM access")}
    tab = request.args.get('tab', 'users')
    if tab == 'stats':
        # статистика живёт на отдельном маршруте — иначе не хватает её данных
        return redirect(url_for('admin_stats'))
    counts = {}
    sizes = {}
    if tab == 'bases' and bases:
        try:
            sizes = _base_sizes(bases)
        except Exception:  # noqa: BLE001
            sizes = {}
        _sync_cluster_state(bases)
        slugs = tuple(b['slug'] for b in bases)
        counts = _cached_swr('counts:' + ','.join(slugs), 120, 3600,
                             lambda: _session_counts(list(slugs)), wait=False)
    pg_mode = _pg_mode_state() if tab == 'bases' else 'off'
    sandboxes_all = _sandbox_active()
    sandbox_details = {}
    for sb in sandboxes_all:
        owner = db().execute("SELECT username, full_name FROM users WHERE id = ?",
                             (sb['user_id'],)).fetchone()
        src = db().execute("SELECT title FROM bases WHERE slug = ?", (sb['source_slug'],)).fetchone()
        sandbox_details.setdefault(sb['source_slug'], []).append({
            'id': sb['id'],
            'slug': sb['slug'],
            'owner': (owner['full_name'] or owner['username']) if owner else '?',
            'owner_login': owner['username'] if owner else '?',
            'source': (src['title'] if src else sb['source_slug']),
            'source_slug': sb['source_slug'],
            'created_at': _dt_ru(sb['created_at']),
            'dump_date': sb['dump_date'] or '',
            'expires_at': _dt_ru(sb['expires_at']),
            'status': sb['status'],
            'size': sb['size'] or '—',
        })
    sandbox_map = {}
    for sb in sandboxes_all:
        sandbox_map.setdefault(sb['source_slug'], []).append(sb)
    orphan_bases = [b for b in bases if b['id'] not in {base_id for _, base_id in links}]
    return render_template('admin.html', users=users, bases=bases, links=links, tab=tab,
                           sessions=counts, sizes=sizes, pg_mode=pg_mode,
                           maint=maintenance.state(),
                           sandboxes=sandboxes_all, sandbox_map=sandbox_map,
                           sandbox_allow_transfer=_setting_get('sandbox_allow_transfer') == '1',
                           sandbox_allow_extend=_setting_get('sandbox_allow_extend') == '1',
                           sandbox_details=sandbox_details,
                           sandbox_users=db().execute(
                               "SELECT id, username, full_name FROM users "
                               "WHERE role = 'client' AND is_active = 1 ORDER BY username").fetchall(),
                           orphan_bases=orphan_bases,
                           refreshed=_cache_stamp('counts:' + ','.join(slugs) if counts else ''))


def _pwd_ok(pwd):
    return len(pwd) >= 8


@app.route('/admin/users', methods=['POST'])
@admin_required
def user_create():
    check_csrf()
    login = (request.form.get('username') or '').strip().lower()
    name = (request.form.get('full_name') or '').strip()
    org = (request.form.get('organization') or '').strip()
    pwd = request.form.get('password') or ''
    role = request.form.get('role') if request.form.get('role') in ('client', 'admin') else 'client'
    if not re.fullmatch(r'[a-z0-9._-]{3,32}', login):
        flash('Логин: 3–32 символа, латиница, цифры, точка, дефис')
        return redirect(url_for('admin', tab='users'))
    if not _pwd_ok(pwd):
        flash('Пароль должен быть не короче 8 символов')
        return redirect(url_for('admin', tab='users'))
    try:
        db().execute("INSERT INTO users(username, full_name, organization, pass_hash, role) VALUES(?,?,?,?,?)",
                     (login, name or login, org, generate_password_hash(pwd), role))
        db().commit()
    except sqlite3.IntegrityError:
        flash('Такой логин уже существует')
        return redirect(url_for('admin', tab='users'))
    audit('user_create', login)
    flash(f'Клиент «{login}» создан')
    return redirect(url_for('admin', tab='users'))


@app.route('/admin/users/<int:uid>', methods=['POST'])
@admin_required
def user_update(uid):
    check_csrf()
    row = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        abort(404)
    action = request.form.get('action')
    if action == 'password':
        pwd = request.form.get('password') or ''
        if not _pwd_ok(pwd):
            flash('Пароль должен быть не короче 8 символов')
        else:
            db().execute("UPDATE users SET pass_hash = ? WHERE id = ?",
                         (generate_password_hash(pwd), uid))
            db().commit()
            audit('user_password', row['username'])
            flash(f'Пароль «{row["username"]}» изменён')
    elif action == 'toggle':
        db().execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (uid,))
        db().commit()
        audit('user_toggle', row['username'])
    elif action == 'vpn_clear':
        db().execute("UPDATE users SET vpn_config = NULL, vpn_enabled = 0 WHERE id = ?", (uid,))
        db().commit()
        audit('vpn_clear', row['username'])
        flash('VPN отключён, конфигурация удалена')
        return redirect(url_for('admin', tab='users'))

    elif action == 'rename':
        name = (request.form.get('full_name') or '').strip()
        org = (request.form.get('organization') or '').strip()

        vpn_on = 1 if request.form.get('vpn_enabled') else 0
        cfg = row['vpn_config'] if 'vpn_config' in row.keys() else None
        upload = request.files.get('vpn_config')
        if upload and upload.filename:
            raw = upload.read(65536)
            text = raw.decode('utf-8', 'replace')
            built, error = _wg_build_config(text)
            if error:
                flash('Конфигурация не сохранена — ' + error)
            else:
                cfg = built
                vpn_on = 1
                saved = _wg_save_file(row['username'], cfg)
                audit('vpn_config', '%s%s' % (row['username'], ' → ' + saved if saved else ''))
                flash('Конфигурация собрана: ключи из файла, маршрут только на '
                      + (_setting_get('vpn_allowed') or '192.168.0.5/32'))

        db().execute("UPDATE users SET full_name = ?, organization = ?, vpn_enabled = ?, vpn_config = ? "
                     "WHERE id = ?", (name, org, vpn_on, cfg, uid))
        db().commit()
        audit('user_rename', row['username'])
        flash(f'Карточка «{row["username"]}» обновлена')
    elif action == 'delete':
        if row['username'] == 'admin':
            flash('Удалить главного администратора нельзя')
        else:
            db().execute("DELETE FROM access WHERE user_id = ?", (uid,))
            db().execute("DELETE FROM users WHERE id = ?", (uid,))
            db().commit()
            audit('user_delete', row['username'])
            flash(f'Пользователь «{row["username"]}» удалён')
    return redirect(url_for('admin', tab='users'))




WG_TEMPLATE = """[Interface]
PrivateKey = {priv}
Address = {addr}
MTU = {mtu}

[Peer]
PublicKey = {pub}{psk}
AllowedIPs = {allowed}
Endpoint = {endpoint}
PersistentKeepalive = {keepalive}
"""

VPN_CLIENTS_DIR = '/opt/1c-portal/vpn-clients'


def _wg_parse(text):
    """Достаёт ключи и адрес из загруженной конфигурации WireGuard."""
    values = {}
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith(';') or line.startswith('['):
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip().lower()] = value.strip()
    return values


def _wg_build_config(text):
    """Собирает правильный конфиг: из файла берём только ключи и адрес.

    Возвращает (конфиг, ошибка). Ошибка — текст для администратора.
    """
    keys = _wg_parse(text)
    priv = keys.get('privatekey', '').strip()
    pub = keys.get('publickey', '').strip()
    psk = keys.get('presharedkey', '').strip()
    addr = keys.get('address', '').strip()

    missing = []
    if not priv or len(priv) < 40:
        missing.append('PrivateKey')
    if not pub or len(pub) < 40:
        missing.append('PublicKey')
    if missing:
        return None, 'в файле нет ключей: ' + ', '.join(missing)

    if '/' not in addr:
        addr = addr.split(',')[0].strip()
        addr = (addr or '10.8.0.2') + '/32'

    cfg = WG_TEMPLATE.format(
        priv=priv,
        addr=addr,
        mtu=_setting_get('vpn_mtu') or '1380',
        pub=pub,
        psk=('\nPresharedKey = %s' % psk) if psk else '',
        allowed=_setting_get('vpn_allowed') or '192.168.0.5/32',
        endpoint=_setting_get('vpn_endpoint') or '1c.dgek.ru:51820',
        keepalive=_setting_get('vpn_keepalive') or '15',
    )
    return cfg, None


def _wg_save_file(username, cfg):
    """Кладёт готовый конфиг в папку клиента на сервере."""
    try:
        os.makedirs(VPN_CLIENTS_DIR, mode=0o750, exist_ok=True)
        path = os.path.join(VPN_CLIENTS_DIR, '%s.conf' % username)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(cfg)
        os.chmod(path, 0o640)
        return path
    except OSError:
        return None



SOFT_DIR = '/opt/1c-portal/soft'
WIREGUARD_FILES = {
    'wireguard-amd64-1.1.1.msi': 'WireGuard для Windows, 64-бит (1.1.1)',
    'wireguard-x86-1.1.1.msi': 'WireGuard для Windows, 32-бит (1.1.1)',
}


@app.route('/download/wireguard/<path:name>')
@login_required
def download_wireguard(name):
    """Установщики WireGuard с нашего сервера: сайт производителя заблокирован в РФ."""
    if name not in WIREGUARD_FILES:
        abort(404)
    row = db().execute("SELECT vpn_enabled, vpn_config FROM users WHERE id = ?",
                       (session['uid'],)).fetchone()
    ready = bool(row and row['vpn_enabled'] and row['vpn_config'])
    if not ready and session.get('role') != 'admin':
        abort(403)
    path = os.path.join(SOFT_DIR, 'wireguard', name)
    if not os.path.exists(path):
        abort(404)
    audit('vpn_soft', name)
    return send_from_directory(os.path.join(SOFT_DIR, 'wireguard'), name,
                               as_attachment=True, conditional=True)


@app.route('/vpn/config')
@login_required
def vpn_config_download():
    row = db().execute("SELECT username, vpn_enabled, vpn_config FROM users WHERE id = ?",
                       (session['uid'],)).fetchone()
    if not row or not row['vpn_enabled'] or not row['vpn_config']:
        abort(404)
    audit('vpn_download', row['username'])
    resp = make_response(row['vpn_config'])
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
    resp.headers['Content-Disposition'] = 'attachment; filename="%s-wireguard.conf"' % row['username']
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/admin/users/<int:uid>/vpn-file')
@admin_required
def admin_vpn_file(uid):
    row = db().execute("SELECT username, vpn_config FROM users WHERE id = ?", (uid,)).fetchone()
    if not row or not row['vpn_config']:
        abort(404)
    resp = make_response(row['vpn_config'])
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
    resp.headers['Content-Disposition'] = 'inline; filename="%s-wireguard.conf"' % row['username']
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/admin/bases', methods=['POST'])
@admin_required
def base_create():
    check_csrf()
    slug = (request.form.get('slug') or '').strip().lower()
    title = (request.form.get('title') or '').strip()
    org = (request.form.get('organization') or '').strip()
    descr = (request.form.get('description') or '').strip()
    url_path = (request.form.get('url_path') or '').strip()
    if not re.fullmatch(r'[a-z0-9_-]{2,32}', slug):
        flash('Код базы: 2–32 символа, латиница, цифры, дефис, подчёркивание')
        return redirect(url_for('admin', tab='bases'))
    if not url_path.startswith('/'):
        url_path = '/WEB/%s/' % slug
    try:
        db_name = (request.form.get('db_name') or '').strip() or slug
        make_db = request.form.get('make_db') == '1'
        state = None
        if make_db:
            code, out = _run_root(['/usr/local/bin/1c-create-base', slug, db_name], timeout=300)
            for line in (out or [])[-3:]:
                flash(line)
            state = 'created' if code == 0 else 'failed'
        db().execute("INSERT INTO bases(slug,title,organization,description,url_path,db_name,cluster_state) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (slug, title or slug, org, descr, url_path, db_name, state))
        if make_db:
            flash('Не забудьте выдать доступ к базе в разделе «Доступы» — иначе клиент увидит отказ.')
        db().commit()
    except sqlite3.IntegrityError:
        flash('База с таким кодом уже есть')
        return redirect(url_for('admin', tab='bases'))
    audit('base_create', slug)
    flash(f'База «{slug}» добавлена')
    return redirect(url_for('admin', tab='bases'))


@app.route('/admin/bases/<int:bid>', methods=['POST'])
@admin_required
def base_update(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ?", (bid,)).fetchone()
    if not row:
        abort(404)
    action = request.form.get('action')
    if action == 'toggle':
        db().execute("UPDATE bases SET is_active = 1 - is_active WHERE id = ?", (bid,))
        db().commit()
        audit('base_toggle', row['slug'])
    elif action == 'delete':
        db().execute("DELETE FROM access WHERE base_id = ?", (bid,))
        db().execute("DELETE FROM bases WHERE id = ?", (bid,))
        db().commit()
        audit('base_delete', row['slug'])
        flash(f'База «{row["slug"]}» удалена')
    elif action == 'edit':
        title = (request.form.get('title') or row['title']).strip()
        org = (request.form.get('organization') or '').strip()
        descr = (request.form.get('description') or '').strip()
        url_path = (request.form.get('url_path') or row['url_path']).strip()
        db_name = (request.form.get('db_name') or row['db_name'] or row['slug']).strip()
        db().execute("UPDATE bases SET title=?, organization=?, description=?, url_path=?, db_name=?, "
                     "auto_user=?, auto_pwd=? WHERE id=?",
                     (title, org, descr, url_path, db_name,
                      (request.form.get('auto_user') or '').strip(),
                      request.form.get('auto_pwd') or '', bid))
        db().commit()
        audit('base_edit', row['slug'])
        flash(f'База «{row["slug"]}» обновлена')
    return redirect(url_for('admin', tab='bases'))


@app.route('/admin/bases/<int:bid>/kick', methods=['POST'])
@admin_required
def base_kick(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ?", (bid,)).fetchone()
    if not row:
        abort(404)
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-kick-sessions', row['slug']],
                              capture_output=True, text=True, timeout=120)
        out = (proc.stdout or proc.stderr or '').strip().splitlines()
        flash(out[-1] if out else ('Код возврата: %s' % proc.returncode))
    except Exception as exc:  # noqa: BLE001
        flash('Не удалось отключить сеансы: %s' % exc)
    audit('base_kick', row['slug'])
    return redirect(url_for('admin', tab='bases'))


def _toggle_jobs(slug):
    """Переключает блокировку регламентных заданий и чистит кэш."""
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-jobs-deny', slug, 'toggle'],
                              capture_output=True, text=True, timeout=60)
        msg = (proc.stdout or proc.stderr or '').strip().splitlines()
        flash(msg[-1] if msg else ('Код возврата: %s' % proc.returncode))
    except Exception as exc:  # noqa: BLE001
        flash('Не удалось изменить блокировку: %s' % exc)
    _cache.clear()
    audit('base_jobs', slug)




def _size_human(value):
    """«2356 MB» -> «2.3 ГБ» для карточек базы."""
    units = {'kB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4}
    try:
        number, unit = value.split()
        return metrics.human_bytes(float(number) * units[unit])
    except (ValueError, KeyError):
        return value


def _base_sizes_fetch(bases):
    """Запрашивает размеры баз в PostgreSQL (медленно во время импорта)."""
    names = sorted({(b['db_name'] or b['slug']) for b in bases})
    if not names:
        return {}
    sizes = {}
    try:
        placeholders = ','.join("'%s'" % n.replace("'", "''") for n in names)
        sql = ("select datname || '|' || pg_size_pretty(pg_database_size(datname)) "
               "from pg_database where datname in (%s)" % placeholders)
        proc = subprocess.run(
            ['sudo', '-n', '-u', 'postgres', '/opt/pgpro/1c-16/bin/psql', '-Atc', sql],
            capture_output=True, text=True, timeout=30)
        for line in (proc.stdout or '').splitlines():
            if '|' in line:
                name, size = line.split('|', 1)
                sizes[name.strip()] = _size_human(size.strip())
    except Exception:  # noqa: BLE001
        sizes = {}
    return sizes


def _base_sizes(bases):
    """Размеры баз из кэша. Никогда не тормозит страницу: обновление идёт в фоне."""
    names = sorted({(b['db_name'] or b['slug']) for b in bases})
    if not names:
        return {}
    key = 'basesize:' + ','.join(names)
    force = has_request_context() and request.args.get('refresh') == '1'
    ttl = 0 if force else 60
    return _cached_swr(key, ttl, 24 * 3600, lambda: _base_sizes_fetch(bases), wait=force)


def warm_sizes():
    """Держит размеры баз в кэше, чтобы кабинет клиента открывался мгновенно."""
    rows = db().execute("SELECT * FROM bases ORDER BY sort_order, title").fetchall()
    if not rows:
        return
    try:
        sizes = _base_sizes_fetch(rows)
        names = sorted({(b['db_name'] or b['slug']) for b in rows})
        if sizes:
            _cache['basesize:' + ','.join(names)] = (time.time(), sizes)
    except Exception:  # noqa: BLE001
        pass


def warm_counts():
    """Обновляет кэш сеансов и состояния баз в фоне, чтобы страница «Базы» не ждала rac."""
    rows = db().execute("SELECT slug FROM bases ORDER BY sort_order, title").fetchall()
    names = [r['slug'] for r in rows]
    if not names:
        return
    key = ','.join(names)
    _cached('counts:' + key, 20, lambda: _session_counts(names))

    def fetch_state():
        try:
            proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-base-state'] + names,
                                  capture_output=True, text=True, timeout=90)
            out = {}
            for line in (proc.stdout or '').splitlines():
                parts = line.split()
                if len(parts) == 2:
                    out[parts[0]] = parts[1] == 'yes'
            return out
        except Exception:  # noqa: BLE001
            return {}

    _cached('basestate:' + key, 240, fetch_state)


def _sync_cluster_state(bases):
    """Сверяет записи портала с кластером 1С и обновляет колонку «БД в кластере»."""
    names = [b['slug'] for b in bases]
    if not names:
        return

    def fetch():
        try:
            proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-base-state'] + names,
                                  capture_output=True, text=True, timeout=60)
            result = {}
            for line in (proc.stdout or '').splitlines():
                parts = line.split()
                if len(parts) == 2:
                    result[parts[0]] = parts[1] == 'yes'
            return result
        except Exception:  # noqa: BLE001
            return {}

    actual = _cached_swr('basestate:' + ','.join(names), 240, 3600, fetch, wait=False)
    if not actual:
        return
    conn = db()
    changed = False
    for base in bases:
        exists = actual.get(base['slug'])
        if exists is None:
            continue
        new_state = 'created' if exists else None
        if (base['cluster_state'] or None) != new_state:
            conn.execute("UPDATE bases SET cluster_state = ? WHERE id = ?", (new_state, base['id']))
            changed = True
    if changed:
        conn.commit()


@app.route('/admin/bases/<int:bid>/republish', methods=['POST'])
@admin_required
def base_republish(bid):
    """Пересоздаёт публикацию одной базы (default.vrd и конфиг Apache)."""
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ?", (bid,)).fetchone()
    if not row:
        abort(404)
    code, out = _run_root(['/usr/local/bin/1c-republish-base', row['slug'],
                           row['db_name'] or row['slug']], timeout=120)
    for line in out[-2:]:
        flash(line)
    if code != 0:
        flash('Публикация не применена — проверьте конфигурацию Apache')
    audit('base_republish', row['slug'])
    return redirect(url_for('admin', tab='bases'))


@app.route('/admin/bases/<int:bid>/jobs', methods=['POST'])
@admin_required
def base_jobs(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ?", (bid,)).fetchone()
    if not row:
        abort(404)
    _toggle_jobs(row['slug'])
    return redirect(url_for('admin', tab='bases'))


def _pg_update_mode(state, slug):
    """Включает или выключает быстрый режим PostgreSQL для обновления базы."""
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-pg-update-mode', state, slug],
                              capture_output=True, text=True, timeout=600)
        out = (proc.stdout or proc.stderr or '').strip().splitlines()
        for line in out[:3]:
            flash(line.strip())
        if proc.returncode != 0 and not out:
            flash('Код возврата: %s' % proc.returncode)
    except Exception as exc:  # noqa: BLE001
        flash('Не удалось изменить режим обновления: %s' % exc)
    _cache.clear()


def _pg_mode_state():
    """Состояние ускорения PostgreSQL: быстрый путь — файл-маркер, иначе скрипт."""
    try:
        with open('/etc/1c-portal/pg-mode.state', encoding='utf-8') as fh:
            value = fh.read().strip()
        if value in ('on', 'off'):
            return value
    except OSError:
        pass
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-pg-update-mode', 'status'],
                              capture_output=True, text=True, timeout=30)
        return 'on' if (proc.stdout or '').strip().startswith('on') else 'off'
    except Exception:  # noqa: BLE001
        return 'off'


@app.route('/admin/bases/<int:bid>/update-mode', methods=['POST'])
@admin_required
def base_update_mode(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ?", (bid,)).fetchone()
    if not row:
        abort(404)
    state = 'off' if request.form.get('mode') == 'off' else 'on'
    _pg_update_mode(state, row['slug'])
    conn = db()
    conn.execute("UPDATE bases SET update_mode = ? WHERE id = ?",
                 (time.strftime('%Y-%m-%d %H:%M:%S') if state == 'on' else None, bid))
    conn.commit()
    audit('base_update_mode', row['slug'] + (' on' if state == 'on' else ' off'))
    return redirect(url_for('admin', tab='bases'))



@app.route('/portal/bases/<int:bid>/jobs', methods=['POST'])
@login_required
def portal_base_jobs(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ? AND is_active = 1", (bid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], bid)).fetchone()
        if not allowed:
            abort(403)
    _toggle_jobs(row['slug'])
    return redirect(url_for('index', sync=1))


@app.route('/admin/access', methods=['POST'])
@admin_required
def access_save():
    check_csrf()
    uid = int(request.form.get('user_id', 0))
    db().execute("DELETE FROM access WHERE user_id = ?", (uid,))
    for bid in request.form.getlist('base_id'):
        db().execute("INSERT OR IGNORE INTO access(user_id, base_id) VALUES(?,?)",
                     (uid, int(bid)))
    db().commit()
    audit('access_update', str(uid))
    flash('Доступы сохранены')
    return redirect(url_for('admin', tab='access'))


def _fmt_dur(sec):
    sec = int(sec or 0)
    if sec <= 0:
        return '—'
    h, rest = divmod(sec, 3600)
    m = rest // 60
    if h:
        return '%d ч %02d мин' % (h, m)
    return '%d мин' % m


app.jinja_env.globals['fmt_dur'] = _fmt_dur
CLIENT_LABELS = {
    'WebClient': 'Веб-клиент',
    '1CV8': 'Толстый клиент',
    '1CV8C': 'Тонкий клиент',
    'Designer': 'Конфигуратор',
    'COMConnection': 'COM-соединение',
    'WSConnection': 'Веб-сервис',
}


def _client_label(app):
    return CLIENT_LABELS.get(app, app or '—')


app.jinja_env.globals['client_label'] = _client_label
app.jinja_env.globals['human_bytes'] = metrics.human_bytes


@app.template_global()
def asset(path):
    """Ссылка на статику с версией — можно кэшировать надолго."""
    return url_for('static', filename=path) + '?v=' + APP_VERSION

def _fmt_dt(value):
    """2026-11-04T22:49:38 -> 2026-11-04 22:49:38"""
    text = (value or '').replace('T', ' ')
    return text[:19]


app.jinja_env.globals['dt'] = _fmt_dt


@app.route('/admin/stats')
@admin_required
def admin_stats():
    users = db().execute("""
        SELECT v.username,
               COUNT(*) AS visits,
               SUM((julianday(COALESCE(v.ended_at, v.last_seen)) - julianday(v.started_at)) * 86400) AS seconds,
               MAX(v.started_at) AS last_login,
               MAX(COALESCE(v.ended_at, v.last_seen)) AS last_seen,
               MAX(CASE WHEN v.ended_at IS NULL THEN 1 ELSE 0 END) AS online,
               COUNT(DISTINCT CASE WHEN v.ip <> '' THEN v.ip END) AS ips,
               (SELECT ip FROM visits v2 WHERE v2.username = v.username ORDER BY v2.id DESC LIMIT 1) AS last_ip
        FROM visits v
        GROUP BY v.username
        ORDER BY last_seen DESC""").fetchall()

    live_sessions = _cached('live', 30, _sessions_snapshot)
    client_history = db().execute("""
        SELECT username, app, host, started_at, first_seen, last_seen
        FROM client_sessions ORDER BY last_seen DESC LIMIT 150""").fetchall()

    vpn_rows = db().execute("""
        SELECT u.username, u.full_name, u.organization, u.vpn_enabled,
               (u.vpn_config IS NOT NULL AND length(u.vpn_config) > 0) AS has_cfg,
               (SELECT MAX(ts) FROM audit a WHERE a.action = 'vpn_download' AND a.actor = u.username) AS last_download,
               (SELECT COUNT(*) FROM audit a WHERE a.action = 'vpn_download' AND a.actor = u.username) AS downloads,
               (SELECT MAX(ts) FROM audit a WHERE a.action = 'vpn_config'
                  AND (a.actor = u.username OR a.details LIKE '%' || u.username || '%')) AS issued_at
        FROM users u
        WHERE u.vpn_enabled = 1 OR (u.vpn_config IS NOT NULL AND length(u.vpn_config) > 0)
        ORDER BY u.username""").fetchall()

    lic = _cached('lic', 60, _licenses)
    srv = metrics.collect()
    try:
        db().execute("INSERT INTO metrics(cpu, rx, tx) VALUES(?,?,?)",
                     (srv['cpu'], srv['net_rx'], srv['net_tx']))
        db().commit()
    except Exception:  # noqa: BLE001
        pass
    history = db().execute("SELECT cpu, rx, tx FROM metrics ORDER BY id DESC LIMIT 60").fetchall()[::-1]
    srv['spark_cpu'] = [r['cpu'] for r in history]
    srv['spark_net'] = []
    prev = None
    for r in history:
        if prev:
            srv['spark_net'].append(max(0, (r['rx'] + r['tx']) - (prev['rx'] + prev['tx'])) / 1024.0 / 1024.0)
        prev = r

    opens = {}
    for r in db().execute("""
            SELECT actor, COUNT(*) AS n, COUNT(DISTINCT details) AS bases
            FROM audit WHERE action = 'open_base' GROUP BY actor"""):
        opens[r['actor']] = {'n': r['n'], 'bases': r['bases']}

    opens_by_base = db().execute("""
        SELECT details AS slug, COUNT(*) AS n, COUNT(DISTINCT actor) AS people
        FROM audit WHERE action = 'open_base' GROUP BY details ORDER BY n DESC""").fetchall()

    events = db().execute("SELECT * FROM audit ORDER BY id DESC LIMIT 300").fetchall()

    visits = db().execute("""
        SELECT username, started_at, last_seen, ended_at, ip,
               (julianday(COALESCE(ended_at, last_seen)) - julianday(started_at)) * 86400 AS seconds
        FROM visits ORDER BY id DESC LIMIT 200""").fetchall()

    total_seconds = db().execute("""
        SELECT COALESCE(SUM((julianday(COALESCE(ended_at, last_seen)) - julianday(started_at)) * 86400), 0)
        FROM visits""").fetchone()[0]

    return render_template('admin.html', users=[], bases=[], links=set(), tab='stats',
                           sessions={},
                           stats_users=users, stats_opens=opens, stats_bases=opens_by_base,
                           stats_events=events, stats_visits=visits,
                           stats_total=total_seconds,
                           stats_live=live_sessions, stats_clients=client_history, srv=srv, lic=lic,
                           stats_vpn=vpn_rows,
                           refreshed=_cache_stamp('live'),
                           stats_visits_count=len(visits))


def _sessions_snapshot():
    """Текущие сеансы 1С + запись их в историю (client_sessions)."""
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-sessions-list'],
                              capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for line in (proc.stdout or '').splitlines():
        parts = line.split('|')
        if len(parts) < 6:
            continue
        rows.append({'sid': parts[0], 'user': parts[1], 'app': parts[2],
                     'host': parts[3], 'started': parts[4], 'last': parts[5]})
    cleared = _setting_get('stats_cleared_at')
    try:
        for r in rows:
            started = (r['started'] or '').replace('T', ' ')[:19]
            # историю не восстанавливаем: сеансы, начатые до очистки, не пишем
            if cleared and started and started < cleared:
                continue
            db().execute("""
                INSERT INTO client_sessions(sid, username, app, host, started_at, last_seen)
                VALUES(?,?,?,?,?,datetime('now','localtime'))
                ON CONFLICT(sid) DO UPDATE SET
                    username = excluded.username, app = excluded.app, host = excluded.host,
                    started_at = excluded.started_at, last_seen = datetime('now','localtime')""",
                         (r['sid'], r['user'], r['app'], r['host'], started))
        db().commit()
    except Exception:  # noqa: BLE001
        pass
    rows.sort(key=lambda x: (x.get('started') or ''), reverse=True)
    return rows


def _setting_get(name):
    try:
        row = db().execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        return row['value'] if row else None
    except Exception:  # noqa: BLE001
        return None


def _setting_set(name, value):
    conn = db()
    conn.execute("INSERT INTO settings(name, value) VALUES(?,?) "
                 "ON CONFLICT(name) DO UPDATE SET value = excluded.value", (name, value))
    conn.commit()


@app.route('/admin/stats/clear', methods=['POST'])
@admin_required
def admin_stats_clear():
    check_csrf()
    conn = db()
    conn.execute("DELETE FROM audit")
    conn.execute("DELETE FROM visits")
    conn.execute("DELETE FROM client_sessions")
    conn.commit()
    _setting_set('stats_cleared_at', time.strftime('%Y-%m-%d %H:%M:%S'))
    audit('stats_clear', 'история очищена')
    flash('История и статистика очищены')
    _cache.clear()
    return redirect(url_for('admin_stats'))


@app.route('/admin/stats/kick', methods=['POST'])
@admin_required
def admin_stats_kick():
    """Отключает всех пользователей 1С от всех опубликованных баз."""
    check_csrf()
    bases = db().execute("SELECT slug FROM bases WHERE is_active = 1").fetchall()
    if not bases:
        flash('Нет активных баз для отключения')
        return redirect(url_for('admin_stats'))
    # отключение идёт в фоне: rac по каждой базе — это десятки секунд
    script = 'for b in %s; do echo "== $b"; /usr/local/bin/1c-kick-sessions "$b"; done' % ' '.join(
        b['slug'] for b in bases)
    jid, _ = _job_start('kick-all', 'Отключение всех пользователей 1С', ['bash', '-lc', script],
                        session.get('uid'))
    audit('stats_kick', 'запущено в фоне: задание %s' % jid)
    flash('Отключение запущено в фоне (задание №%s). Прогресс — в «Заданиях».' % jid)
    return redirect(url_for('admin_jobs'))



DEFAULT_SETTINGS = {
    'ic_host': os.environ.get('PORTAL_IC_HOST', '1c.dgek.ru'),
    'portal_server_name': os.environ.get('PORTAL_SERVER_NAME', '1c.dgek.ru'),
    'db_host': '127.0.0.1',
    'db_port': '5432',
    'db_user': 'postgres',
    'pg_admin_user': 'postgres',
    'mm_hook': os.environ.get('PORTAL_MM_LOGIN_HOOK', ''),
    'mm_login_alerts': '1',
    'backup_enabled': '1',
    'backup_time': '04:00',
    'backup_keep': '14',
    'backup_dir': '/var/lib/1c-backups',
    'backup_user': '',
    'backup_pass': '',
    'vpn_endpoint': '1c.dgek.ru:51820',
    'vpn_allowed': '192.168.0.5/32',
    'vpn_mtu': '1380',
    'vpn_keepalive': '15',
    'ic_server_name': 'srv.1c.dgek.ru',
    'monitor_enabled': '1',
    'monitor_url': 'https://1c.dgek.ru/healthz',
    'monitor_hook': '',
    'monitor_threshold': '2',
    'monitor_disk_min_gb': '10',
    'monitor_backup_max_h': '28',
    'monitor_resolve': '1c.dgek.ru:443:192.168.0.15',
    'sandbox_enabled': '0',
    'sandbox_keep_days': '3',
    'sandbox_max_active': '1',
    'sandbox_min_free_gb': '8',
    'sandbox_allow_transfer': '1',
    'sandbox_allow_extend': '1',
    'trusted_days': '30',
    'cluster_user': 'arshin',
    'cluster_pwd': '',
    'cluster_uuid': 'e3220a07-7374-4fc0-b4fb-25ace3789930',
}


def _settings_all():
    values = dict(DEFAULT_SETTINGS)
    try:
        for row in db().execute("SELECT name, value FROM settings").fetchall():
            if row['name'] in values and row['value']:
                values[row['name']] = row['value']
    except Exception:  # noqa: BLE001
        pass
    return values


def _run_root(args, timeout=300):
    """Выполняет служебный скрипт через sudo, возвращает код и строки вывода."""
    try:
        proc = subprocess.run(['sudo', '-n'] + args, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or proc.stderr or '').strip().splitlines()
        return proc.returncode, out
    except Exception as exc:  # noqa: BLE001
        return 1, [str(exc)]


PG_PASS_TMP = '/etc/1c-portal/.pg-pass'


def _pg_password_set():
    try:
        return os.path.exists('/etc/1c-portal/pg-admin.conf')
    except OSError:
        return False


def _write_settings_json(password=None):
    """Сохраняет параметры для скрипта применения настроек. Возвращает True при успехе."""
    import json
    data = _settings_all()
    try:
        bases = {}
        for row in db().execute("SELECT slug, db_name FROM bases").fetchall():
            bases[row['slug']] = row['db_name'] or row['slug']
        data['bases'] = bases
        os.makedirs('/etc/1c-portal', exist_ok=True)
        path = '/etc/1c-portal/settings.json'
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        try:
            os.chmod(path, 0o640)
        except OSError:
            pass
        if password:
            # пароль передаётся скрипту отдельным файлом и сразу удаляется им
            with open(PG_PASS_TMP, 'w', encoding='utf-8') as fh:
                fh.write(password)
            try:
                os.chmod(PG_PASS_TMP, 0o600)
            except OSError:
                pass
        return True
    except Exception as exc:  # noqa: BLE001
        flash('Не удалось сохранить файл настроек: %s' % exc)
        return False


def _schedule_state():
    code, out = _run_root(['/usr/local/bin/1c-restart-schedule', 'status'], timeout=30)
    if out and out[0] and out[0] != 'off':
        return ' '.join(out[0].split()[:5])
    return ''



def _backup_info():
    """Состояние архивации: каталог, свободное место, последний запуск."""
    def fetch():
        try:
            proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-backup-info'],
                                  capture_output=True, text=True, timeout=40)
            return json.loads(proc.stdout or '{}')
        except Exception:  # noqa: BLE001
            return {}

    return _cached('backupinfo', 30, fetch)




def _monitor_status():
    """Последняя проверка мониторинга из файла, который пишет 1c-monitor."""
    try:
        with open('/etc/1c-portal/monitor-status.json', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


@app.route('/admin/settings/monitor', methods=['POST'])
@admin_required
def admin_settings_monitor():
    check_csrf()
    url = (request.form.get('monitor_url') or '').strip()
    hook = (request.form.get('monitor_hook') or '').strip()
    resolve = (request.form.get('monitor_resolve') or '').strip()
    threshold = (request.form.get('monitor_threshold') or '').strip()
    disk_min = (request.form.get('monitor_disk_min_gb') or '').strip()
    backup_max = (request.form.get('monitor_backup_max_h') or '').strip()

    if not url.startswith(('http://', 'https://')):
        flash('Адрес проверки должен начинаться с http:// или https://')
        return redirect(url_for('admin_settings'))
    if hook and not hook.startswith('https://'):
        flash('Хук Mattermost должен начинаться с https://')
        return redirect(url_for('admin_settings'))
    if resolve and not re.fullmatch(r'[a-zA-Z0-9._-]+:\d{2,5}:(\d{1,3}\.){3}\d{1,3}', resolve):
        resolve = '1c.dgek.ru:443:192.168.0.15'
    threshold = threshold if threshold.isdigit() and 1 <= int(threshold) <= 10 else '2'
    disk_min = disk_min if disk_min.isdigit() and 1 <= int(disk_min) <= 500 else '10'
    backup_max = backup_max if backup_max.isdigit() and 1 <= int(backup_max) <= 240 else '28'

    _setting_set('monitor_enabled', '1' if request.form.get('monitor_enabled') else '0')
    _setting_set('monitor_url', url)
    _setting_set('monitor_hook', hook)
    _setting_set('monitor_resolve', resolve)
    _setting_set('monitor_threshold', threshold)
    _setting_set('monitor_disk_min_gb', disk_min)
    _setting_set('monitor_backup_max_h', backup_max)
    _write_settings_json()
    _cache.clear()
    audit('settings_monitor', '%s | порог %s' % (url, threshold))
    flash('Мониторинг: %s, проверка %s, порог %s' % (
        'включён' if request.form.get('monitor_enabled') else 'выключен', url, threshold))
    return redirect(url_for('admin_settings'))



@app.route('/admin/settings/monitor-test', methods=['POST'])
@admin_required
def admin_settings_monitor_test():
    """Тестовое сообщение в хук мониторинга — проверка, что уведомления доходят."""
    check_csrf()
    code, out = _run_root(['/usr/local/bin/1c-monitor', 'notify-test'], timeout=60)
    ok = (out or [''])[-1].strip() == 'ok' if out else code == 0
    audit('monitor_test', 'ok' if ok else 'fail')
    if ok:
        flash('Тестовое сообщение отправлено в хук мониторинга')
    else:
        flash('Не удалось отправить: проверьте хук в настройках и журнал /var/log/1c-monitor.log')
    return redirect(url_for('admin_settings'))



@app.route('/admin/settings/monitor-run', methods=['POST'])
@admin_required
def admin_settings_monitor_run():
    check_csrf()
    code, out = _run_root(['/usr/local/bin/1c-monitor', 'check'], timeout=120)
    st = _monitor_status()
    if st.get('ok'):
        flash('Проверка пройдена: ' + ', '.join(c['title'] for c in st.get('checks', []) if c['ok']))
    else:
        bad = [c for c in st.get('checks', []) if not c['ok']]
        for c in bad[:3]:
            flash('%s — %s' % (c['title'], c['detail']))
        if not bad:
            flash('Проверка не выполнена (код %s)' % code)
    audit('monitor_run', 'ok' if st.get('ok') else 'fail')
    _cache.clear()
    return redirect(url_for('admin_settings'))



@app.route('/admin/settings/vpn', methods=['POST'])
@admin_required
def admin_settings_vpn():
    check_csrf()
    endpoint = (request.form.get('vpn_endpoint') or '').strip()
    allowed = (request.form.get('vpn_allowed') or '').strip()
    mtu = (request.form.get('vpn_mtu') or '').strip()
    keepalive = (request.form.get('vpn_keepalive') or '').strip()
    server_name = (request.form.get('ic_server_name') or '').strip()

    if not re.fullmatch(r'[a-zA-Z0-9._-]+:\d{2,5}', endpoint):
        flash('Адрес VPN-сервера: имя:порт, например 1c.dgek.ru:51820')
        return redirect(url_for('admin_settings'))

    # AllowedIPs в WireGuard — только IP или подсеть: имя там работать не будет
    if not re.fullmatch(r'(\d{1,3}\.){3}\d{1,3}/\d{1,2}(,\s*(\d{1,3}\.){3}\d{1,3}/\d{1,2})*', allowed):
        flash('Маршрут VPN должен быть IP-подсетью (например 192.168.0.5/32). '
              'Имя сервера здесь не поддерживается самим WireGuard.')
        return redirect(url_for('admin_settings'))

    if not mtu.isdigit() or not (1280 <= int(mtu) <= 1500):
        mtu = '1380'
    if not keepalive.isdigit() or not (0 <= int(keepalive) <= 120):
        keepalive = '15'
    if not re.fullmatch(r'[a-zA-Z0-9._-]{3,80}', server_name):
        server_name = 'srv.1c.dgek.ru'

    _setting_set('vpn_endpoint', endpoint)
    _setting_set('vpn_allowed', allowed)
    _setting_set('vpn_mtu', mtu)
    _setting_set('vpn_keepalive', keepalive)
    _setting_set('ic_server_name', server_name)
    _write_settings_json()
    _cache.clear()
    audit('settings_vpn', '%s | %s | MTU %s' % (endpoint, allowed, mtu))
    flash('VPN: сервер %s, маршрут %s, MTU %s' % (endpoint, allowed, mtu))
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/backup', methods=['POST'])
@admin_required
def admin_settings_backup():
    check_csrf()
    time_val = (request.form.get('backup_time') or '04:00').strip()
    if not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', time_val):
        time_val = '04:00'
    keep = (request.form.get('backup_keep') or '14').strip()
    keep = str(max(1, min(365, int(keep)))) if keep.isdigit() else '14'
    folder = (request.form.get('backup_dir') or '/var/lib/1c-backups').strip()

    _setting_set('backup_enabled', '1' if request.form.get('backup_enabled') else '0')
    _setting_set('backup_time', time_val)
    _setting_set('backup_keep', keep)
    _setting_set('backup_dir', folder)
    _setting_set('backup_user', (request.form.get('backup_user') or '').strip())
    pwd = (request.form.get('backup_pass') or '').strip()
    if pwd:
        _setting_set('backup_pass', pwd)

    _write_settings_json()
    _cache.clear()
    audit('settings_backup', '%s keep=%s dir=%s' % (time_val, keep, folder))
    flash('Архивация: %s в %s, хранить %s копий, каталог %s' % (
        'включена' if request.form.get('backup_enabled') else 'выключена', time_val, keep, folder))
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/backup-run', methods=['POST'])
@admin_required
def admin_settings_backup_run():
    check_csrf()
    jid, slug = _job_start('backup', 'Архивация баз 1С', ['/usr/local/bin/1c-backup.sh', 'run'],
                           session.get('uid'))
    audit('backup_run', 'запущено в фоне: %s' % slug)
    flash('Архивация запущена в фоне. Прогресс и лог — на странице «Задания» или в карточке «Архивация».')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/mm', methods=['POST'])
@admin_required
def admin_settings_mm():
    check_csrf()
    hook = (request.form.get('mm_hook') or '').strip()
    _setting_set('mm_hook', hook)
    _setting_set('mm_login_alerts', '1' if request.form.get('mm_login_alerts') else '0')
    _cache.clear()
    audit('settings_mm', 'login_alerts=%s' % request.form.get('mm_login_alerts'))
    flash('Настройки уведомлений сохранены' if hook else 'Хук очищен — уведомления отключены')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/mm-test', methods=['POST'])
@admin_required
def admin_settings_mm_test():
    check_csrf()
    ok = _mm_notify('#### ✅ Портал 1С: проверка уведомлений\n\n'
                    'Настройка Mattermost работает. Это тестовое сообщение.')
    flash('Тестовое сообщение отправлено в Mattermost' if ok
          else 'Не удалось отправить: проверьте адрес хука')
    audit('settings_mm_test', 'ok' if ok else 'fail')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        check_csrf()
        for name in ('ic_host', 'portal_server_name', 'db_host', 'db_port', 'db_user', 'pg_admin_user'):
            value = (request.form.get(name) or '').strip()
            if value:
                _setting_set(name, value)
        password = (request.form.get('pg_admin_password') or '').strip()
        if not _write_settings_json(password or None):
            return redirect(url_for('admin_settings'))
        code, out = _run_root(['/usr/local/bin/1c-apply-settings'], timeout=120)
        for line in out[-3:]:
            flash(line)
        if code != 0:
            flash('Настройки сохранены, но применить к публикации не удалось')
        audit('settings_save', 'параметры подключения')
        _cache.clear()
        return redirect(url_for('admin_settings'))

    return render_template('admin.html', users=[], bases=[], links=set(), tab='settings',
                           settings=_settings_all(), schedule=_schedule_state(),
                           maint=maintenance.state(), auto_maint=maintenance.auto_settings(),
                           pg_password_set=_pg_password_set(),
                           monitor=_monitor_status(),
                           sandbox_allow_transfer=_setting_get('sandbox_allow_transfer') == '1',
                           sandbox_allow_extend=_setting_get('sandbox_allow_extend') == '1',
                           twofa_enabled=bool((db().execute(
                               "SELECT totp_enabled FROM users WHERE id = ?",
                               (session['uid'],)).fetchone() or {'totp_enabled': 0})['totp_enabled']),
                           backup=_backup_info(),
                           backup_pass_set=_setting_get('backup_pass') != '',
                           refreshed=time.strftime('%H:%M:%S'))


@app.route('/admin/settings/schedule', methods=['POST'])
@admin_required
def admin_settings_schedule():
    check_csrf()
    mode = (request.form.get('cron') or '').strip() or 'off'
    if mode != 'off' and len(mode.split()) != 5:
        flash('Расписание должно состоять из пяти полей cron, например: 0 3 * * *')
        return redirect(url_for('admin_settings'))
    code, out = _run_root(['/usr/local/bin/1c-restart-schedule', mode], timeout=60)
    flash(out[-1] if out else 'готово')
    audit('settings_schedule', mode)
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/restart-1c', methods=['POST'])
@admin_required
def admin_settings_restart():
    check_csrf()
    code, out = _run_root(['/usr/local/bin/1c-safe-restart', 'apply'], timeout=600)
    for line in out[-4:]:
        flash(line)
    audit('settings_restart_1c', 'перезапуск сервера 1С')
    _cache.clear()
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/reboot', methods=['POST'])
@admin_required
def admin_settings_reboot():
    check_csrf()
    audit('settings_reboot', 'перезагрузка сервера')
    db().commit()
    subprocess.Popen(['sudo', '-n', '/usr/bin/systemctl', 'reboot'])
    return Response(
        '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Перезагрузка</title></head>'
        '<body style="font:16px Arial;padding:40px"><h1>Сервер перезагружается</h1>'
        '<p>Портал вернётся через 1-3 минуты. Обновите страницу позже.</p></body></html>',
        status=202, mimetype='text/html')



@app.after_request
def _no_store(response):
    """Страницы портала не кэшируются браузером — иначе видно устаревшее состояние."""
    # кэшируем только статику веб-клиента (скрипты, стили, картинки, строки ресурсов),
    # а динамические ответы 1С (logForm, moxel, tempstorage, ping) — никогда:
    # иначе браузер подставляет устаревшие данные и печатная форма остаётся пустой
    if request.path.startswith('/WEB/'):
        low = request.path.lower()
        query = request.query_string.decode('latin-1').lower()
        static_ext = ('.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
                      '.woff', '.woff2', '.ico', '.map')
        # неизменяемое: файлы клиента и всё, что версионировано параметром
        immutable = (low.endswith(static_ext) or '/scripts/' in low or 'resourcestrings' in low
                     or 'confver=' in query or 'sysver=' in query or 'version=' in query)
        # состояние сеанса и печати кэшировать нельзя никогда
        volatile = ('/e1cib/tempstorage', '/e1cib/ping', '/e1cib/logform',
                    '/e1cib/moxel', '/e1csys/cn', '/e1cib/command', '/e1cib/modules/call')
        if immutable and not any(mark in low for mark in volatile):
            return response
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        return response
    if request.path.startswith('/static/'):
        return response
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response



@app.route('/maintenance')
def maintenance_page():
    st = maintenance.state()
    if st.get('phase') != 'active':
        return redirect(url_for('login'))
    return render_template('maintenance.html', st=st)


@app.route('/api/maint')
def api_maint():
    if not session.get('uid'):
        return {'phase': 'none'}
    return maintenance.state()


@app.route('/admin/maintenance', methods=['POST'])
@admin_required
def admin_maintenance_start():
    check_csrf()
    ok, message = maintenance.create(
        request.form.get('starts_at'), request.form.get('ends_at'),
        (request.form.get('message') or '').strip(),
        (request.form.get('comment') or '').strip(),
        session.get('user', ''))
    flash(message)
    audit('maintenance_start', '%s..%s' % (request.form.get('starts_at'), request.form.get('ends_at')))
    return redirect(request.form.get('next') or url_for('admin', tab='bases'))


@app.route('/admin/maintenance/cancel', methods=['POST'])
@admin_required
def admin_maintenance_cancel():
    check_csrf()
    if maintenance.state().get('phase') in ('active', 'grace'):
        maintenance.stop_now('отменено администратором')
    else:
        maintenance.cancel()
    flash('Регламентные работы отменены')
    audit('maintenance_cancel', '')
    return redirect(request.form.get('next') or url_for('admin', tab='bases'))


@app.route('/admin/maintenance/schedule', methods=['POST'])
@admin_required
def admin_maintenance_schedule():
    check_csrf()
    enabled = '1' if request.form.get('enabled') == '1' else '0'
    _setting_set('maint_auto', enabled)
    _setting_set('maint_auto_weekday', (request.form.get('weekday') or '5').strip())
    _setting_set('maint_auto_time', (request.form.get('time') or '03:00').strip())
    _setting_set('maint_auto_minutes', (request.form.get('minutes') or '60').strip())
    flash('Расписание регламентных работ сохранено' if enabled == '1' else 'Автоматические работы отключены')
    audit('maintenance_schedule', enabled)
    return redirect(url_for('admin', tab='bases'))


@app.route('/admin/maintenance/kick', methods=['POST'])
@admin_required
def admin_maintenance_kick():
    check_csrf()
    for line in maintenance.kick_all():
        flash(line)
    audit('maintenance_kick', 'отключение всех сеансов')
    return redirect(request.form.get('next') or url_for('admin', tab='bases'))



@app.route('/admin/maintenance/now', methods=['POST'])
@admin_required
def admin_maintenance_now():
    check_csrf()
    tune = request.form.get('tune') == '1'
    ok, message = maintenance.start_now(
        request.form.get('minutes') or 30,
        (request.form.get('comment') or '').strip(),
        session.get('user', ''), tune=tune)
    flash(message)
    audit('maintenance_now', 'минут: %s, tune=%s' % (request.form.get('minutes'), tune))
    return redirect(request.form.get('next') or url_for('admin', tab='bases'))


@app.route('/admin/maintenance/stop', methods=['POST'])
@admin_required
def admin_maintenance_stop():
    check_csrf()
    ok, message = maintenance.stop_now('остановлено администратором')
    flash(message)
    audit('maintenance_stop', '')
    return redirect(request.form.get('next') or url_for('admin', tab='bases'))


@app.route('/portal/bases/<int:bid>/update-mode', methods=['POST'])
@login_required
def portal_base_update_mode(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ? AND is_active = 1", (bid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], bid)).fetchone()
        if not allowed:
            abort(403)
    state = 'off' if request.form.get('mode') == 'off' else 'on'
    try:
        proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-pg-update-mode', state, row['slug']],
                              capture_output=True, text=True, timeout=600)
        out = (proc.stdout or proc.stderr or '').strip().splitlines()
        for line in out[:2]:
            flash(line.strip())
    except Exception as exc:  # noqa: BLE001
        flash('Не удалось изменить режим: %s' % exc)
    _cache.clear()
    audit('base_update_mode', '%s %s' % (row['slug'], state))
    return redirect(url_for('index'))



@app.route('/bases/<int:bid>/v8i')
@login_required
def base_v8i(bid):
    row = db().execute("SELECT * FROM bases WHERE id = ? AND is_active = 1", (bid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], bid)).fetchone()
        if not allowed:
            abort(403)
    # в файле .v8i не должно быть внутреннего IP: клиент ходит на имя сервера через VPN
    host = _setting_get('ic_server_name') or 'srv.1c.dgek.ru'
    ref = row['db_name'] or row['slug']
    text = ('[Соединение с сервером 1С:Предприятие]\r\n'
            'Connect=Srvr="%s";Ref="%s";\r\n' % (host, ref))
    data = text.encode('cp1251', 'replace')
    audit('base_v8i', row['slug'])
    return Response(data, mimetype='application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="%s.v8i"' % row['slug'],
    })


@app.errorhandler(403)
def _e403(exc):
    return render_template('error.html', code=403, title='Нет доступа к этой базе',
                           message='У вашей учётной записи портала нет прав на эту базу 1С.',
                           hint='Попросите администратора портала добавить доступ в разделе '
                                '«Доступы» — после этого база появится в личном кабинете.'), 403


@app.errorhandler(404)
def _e404(exc):
    return render_template('error.html', code=404, title='Страница не найдена',
                           message='Такого адреса на портале нет или база была удалена.',
                           hint='Проверьте адрес или вернитесь в личный кабинет.'), 404


@app.errorhandler(500)
def _e500(exc):
    return render_template('error.html', code=500, title='Ошибка портала',
                           message='Внутренняя ошибка. Администратор уже видит её в журнале.',
                           hint='Попробуйте обновить страницу через минуту.'), 500


@app.route('/healthz')


def healthz():
    return 'ok', 200



# ===== двухфакторный вход (TOTP) =====

TOTP_STEP = 30
TOTP_DIGITS = 6


def _totp_at(secret, counter, digits=TOTP_DIGITS):
    key = base64.b32decode(secret.upper() + '=' * ((8 - len(secret) % 8) % 8))
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0f
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    return str(value % (10 ** digits)).zfill(digits)


def _totp_verify(secret, code, window=1):
    code = (code or '').strip().replace(' ', '')
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    counter = int(time.time()) // TOTP_STEP
    return any(_totp_at(secret, counter + shift) == code for shift in range(-window, window + 1))


def _totp_new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _totp_uri(secret, username, host):
    label = '%s@%s' % (username, host)
    return 'otpauth://totp/%s?secret=%s&issuer=%s&digits=%d&period=%d' % (
        quote(label, safe=''), secret, quote('Портал 1С ' + host, safe=''), TOTP_DIGITS, TOTP_STEP)


def _backup_codes_new(count=10):
    codes = [secrets.token_hex(4) for _ in range(count)]
    return codes, json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes])


def _backup_code_check(stored, code):
    if not stored:
        return False, stored
    try:
        hashes = json.loads(stored)
    except Exception:  # noqa: BLE001
        return False, stored
    digest = hashlib.sha256((code or '').strip().lower().encode()).hexdigest()
    if digest in hashes:
        hashes.remove(digest)
        return True, json.dumps(hashes)
    return False, stored


def _finish_login(user):
    session.clear()
    session['uid'] = user['id']
    session['user'] = user['username']
    session['name'] = user['full_name'] or user['username']
    session['role'] = user['role']
    session.permanent = True
    cur = db().execute("INSERT INTO visits(username, ip, ua) VALUES(?,?,?)",
                       (user['username'], _client_ip(),
                        (request.headers.get('User-Agent') or '')[:200]))
    db().commit()
    session['visit'] = cur.lastrowid
    session['seen'] = int(time.time())
    _login_ok(user['username'], _client_ip())
    audit('login', _client_ip())


@app.route('/login/2fa', methods=['POST'])
def login_2fa():
    check_csrf()
    uid = session.get('pending_uid')
    started = int(session.get('pending_at') or 0)
    if not uid or time.time() - started > 300:
        session.clear()
        flash('Время подтверждения истекло, войдите заново')
        return redirect(url_for('login'))
    row = db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,)).fetchone()
    if not row:
        session.clear()
        return redirect(url_for('login'))
    code = request.form.get('code') or ''
    ok = _totp_verify(row['totp_secret'], code)
    if not ok and row['totp_backup']:
        ok, left = _backup_code_check(row['totp_backup'], code)
        if ok:
            db().execute("UPDATE users SET totp_backup = ? WHERE id = ?", (left, uid))
            db().commit()
            audit('login_2fa_backup', row['username'])
    if not ok:
        _login_fail(row['username'], _client_ip())
        audit('login_2fa_failed', row['username'])
        return render_template('two_factor.html', error='Неверный код. Проверьте время на телефоне.')
    nxt = session.get('pending_next') or '/'
    _finish_login(row)
    audit('login_2fa', row['username'])
    return redirect(nxt if nxt.startswith('/') else '/')


@app.route('/admin/settings/2fa')
@admin_required
def admin_2fa_page():
    row = db().execute("SELECT * FROM users WHERE id = ?", (session['uid'],)).fetchone()
    if not row:
        abort(404)
    secret = row['totp_secret'] or _totp_new_secret()
    if not row['totp_secret']:
        db().execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, row['id']))
        db().commit()
    uri = _totp_uri(secret, row['username'], request.host.split(':')[0])
    qr = ''
    try:
        proc = subprocess.run(['qrencode', '-t', 'PNG', '-s', '7', '-m', '2', '-o', '-', uri],
                              capture_output=True, timeout=10)
        if proc.returncode == 0 and proc.stdout:
            qr = 'data:image/png;base64,' + base64.b64encode(proc.stdout).decode('ascii')
    except Exception:  # noqa: BLE001
        qr = ''
    return render_template('twofa_setup.html', qr=qr, secret=secret,
                           enabled=bool(row['totp_enabled']),
                           backup_left=len(json.loads(row['totp_backup'] or '[]')),
                           username=row['username'])


@app.route('/admin/settings/2fa/enable', methods=['POST'])
@admin_required
def admin_2fa_enable():
    check_csrf()
    row = db().execute("SELECT * FROM users WHERE id = ?", (session['uid'],)).fetchone()
    code = request.form.get('code') or ''
    if not row or not row['totp_secret'] or not _totp_verify(row['totp_secret'], code):
        flash('Код не подошёл. Проверьте время на телефоне и попробуйте снова.')
        return redirect(url_for('admin_2fa_page'))
    codes, hashed = _backup_codes_new()
    db().execute("UPDATE users SET totp_enabled = 1, totp_backup = ? WHERE id = ?", (hashed, row['id']))
    db().commit()
    audit('2fa_enabled', row['username'])
    return render_template('twofa_setup.html', enabled=True, codes=codes, backup_left=len(codes),
                           secret=row['totp_secret'], qr='', username=row['username'])


@app.route('/admin/settings/2fa/disable', methods=['POST'])
@admin_required
def admin_2fa_disable():
    check_csrf()
    row = db().execute("SELECT * FROM users WHERE id = ?", (session['uid'],)).fetchone()
    code = request.form.get('code') or ''
    password = request.form.get('password') or ''
    by_code = bool(row and row['totp_secret'] and _totp_verify(row['totp_secret'], code))
    by_pwd = bool(row and password and check_password_hash(row['pass_hash'], password))
    if not (by_code or by_pwd):
        flash('Чтобы отключить 2FA, введите код из приложения или свой пароль портала')
        return redirect(url_for('admin_2fa_page'))
    db().execute("UPDATE users SET totp_enabled = 0, totp_secret = NULL, totp_backup = NULL WHERE id = ?",
                 (row['id'],))
    db().commit()
    audit('2fa_disabled', row['username'])
    flash('Двухфакторный вход отключён')
    return redirect(url_for('admin_settings'))



# ===== песочница восстановления =====

SANDBOX_DIR = '/mnt/1cbackup'


def _sandbox_copies(db_name):
    """Все копии базы из каталога архивации: и ночные, и ручные.

    Сначала смотрим каталог, а если он недоступен процессу портала —
    берём индекс, который пишет скрипт архивации (/etc/1c-portal/backup-files.json).
    """
    import glob

    def human(size):
        if not size:
            return '—'
        return '%.1f ГБ' % (size / 1024 ** 3) if size > 1024 ** 3 else '%.0f МБ' % (size / 1024 ** 2)

    found = {}
    for path in glob.glob(os.path.join(SANDBOX_DIR, '%s-*.dump' % db_name)):
        name = os.path.basename(path)
        try:
            size = os.path.getsize(path)
            mtime = os.path.getmtime(path)
        except OSError:
            size, mtime = 0, 0
        when = time.strftime('%d.%m.%Y %H:%M', time.localtime(mtime)) if mtime else name
        found[name] = {'path': path, 'name': name, 'when': when, 'size': size, 'size_h': human(size)}

    if not found:
        try:
            import json
            data = json.load(open('/etc/1c-portal/backup-files.json', encoding='utf-8'))
            for item in data.get('files', []):
                if item.get('base') == db_name:
                    found[item['name']] = {
                        'path': item['path'], 'name': item['name'], 'when': item.get('when') or item['name'],
                        'size': item.get('size') or 0, 'size_h': human(item.get('size') or 0)}
        except Exception:  # noqa: BLE001
            pass

    return [found[k] for k in sorted(found, reverse=True)]


def _sandbox_active(user_id=None):
    sql = ("SELECT s.*, b.title AS sandbox_title, src.title AS source_title, "
           "u.full_name AS owner_name, u.username AS owner_login "
           "FROM sandboxes s "
           "LEFT JOIN bases b ON b.id = s.base_id "
           "LEFT JOIN bases src ON src.slug = s.source_slug "
           "LEFT JOIN users u ON u.id = s.user_id "
           "WHERE s.status IN ('creating','ready')")
    args = ()
    if user_id is not None:
        sql += " AND s.user_id = ?"
        args = (user_id,)
    return db().execute(sql + " ORDER BY s.id DESC", args).fetchall()


def _sandbox_free_gb():
    try:
        st = os.statvfs('/var/lib/pgpro')
        return st.f_bavail * st.f_frsize / 1024 ** 3
    except OSError:
        return 0.0


def _sandbox_run_async(sandbox_id, source_db, new_slug, dump_path):
    def work():
        with app.app_context():
            conn = db()
            try:
                code, out = _run_root(['/usr/local/bin/1c-sandbox', 'create', source_db, new_slug, dump_path],
                                      timeout=3600)
                ok = code == 0
                tail = ' | '.join((out or [])[-3:])[:400]
                conn.execute("UPDATE sandboxes SET status = ?, error = ? WHERE id = ?",
                             ('ready' if ok else 'failed', None if ok else tail, sandbox_id))
                conn.commit()
                if not ok:
                    conn.execute("UPDATE bases SET is_active = 0 WHERE slug = ?", (new_slug,))
                    conn.commit()
                _mm_notify('### Песочница %s\n\n%s\n%s' % (
                    'готова' if ok else 'не создана', new_slug, tail))
            except Exception as exc:  # noqa: BLE001
                try:
                    conn.execute("UPDATE sandboxes SET status = 'failed', error = ? WHERE id = ?",
                                 (str(exc)[:300], sandbox_id))
                    conn.commit()
                except Exception:  # noqa: BLE001
                    pass
            finally:
                conn.close()

    threading.Thread(target=work, daemon=True).start()



def _sandbox_run_job(sandbox_id, source_db, new_slug, dump_path):
    """Создание песочницы как задание с логом."""
    def done(code, path):
        conn = db()
        try:
            tail = ''
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    tail = ' | '.join(f.read().splitlines()[-3:])[:400]
            except OSError:
                pass
            ok = code == 0
            conn.execute("UPDATE sandboxes SET status = ?, error = ? WHERE id = ?",
                         ('ready' if ok else 'failed', None if ok else tail, sandbox_id))
            if not ok:
                conn.execute("UPDATE bases SET is_active = 0 WHERE slug = ?", (new_slug,))
            conn.commit()
            _mm_notify('### Песочница %s\n\n%s\n%s' % ('готова' if ok else 'не создана', new_slug, tail))
        finally:
            conn.close()

    return _job_start('sandbox', 'Создание песочницы %s' % new_slug,
                      ['/usr/local/bin/1c-sandbox', 'create', source_db, new_slug, dump_path],
                      ref=str(sandbox_id), on_done=done)


@app.route('/bases/<int:bid>/copies')
@login_required
def base_copies(bid):
    row = db().execute("SELECT * FROM bases WHERE id = ? AND is_active = 1 AND is_sandbox = 0",
                       (bid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], bid)).fetchone()
        if not allowed:
            abort(403)
    mine = _sandbox_active(session['uid'])
    return {'base': row['slug'], 'copies': _sandbox_copies(row['db_name'] or row['slug']),
            'enabled': _setting_get('sandbox_enabled') == '1',
            'keep_days': int(_setting_get('sandbox_keep_days') or 3),
            'existing': ({'slug': mine[0]['slug'], 'expires': _dt_ru(mine[0]['expires_at']),
                          'source': mine[0]['source_slug']} if mine else None)}


@app.route('/bases/<int:bid>/sandbox', methods=['POST'])
@login_required
def base_sandbox_create(bid):
    check_csrf()
    row = db().execute("SELECT * FROM bases WHERE id = ? AND is_active = 1 AND is_sandbox = 0",
                       (bid,)).fetchone()
    if not row:
        abort(404)
    if _setting_get('sandbox_enabled') != '1':
        flash('Восстановление в песочницу выключено администратором')
        return redirect('/')
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], bid)).fetchone()
        if not allowed:
            abort(403)

    existing = _sandbox_active(session['uid'])
    if existing and request.form.get('replace_old') != '1':
        flash('У вас уже есть песочница «%s». Удалите её, чтобы создать новую.' % existing[0]['slug'])
        return redirect('/')
    if existing:
        # клиент подтвердил: старая песочница удаляется вместе с данными
        old_sb = existing[0]
        code, out = _run_root(['/usr/local/bin/1c-sandbox', 'drop', old_sb['slug']], timeout=900)
        if code != 0:
            tail = ' | '.join((out or [])[-2:])[:200]
            flash('Не удалось удалить старую песочницу: %s' % tail)
            return redirect('/')
        conn0 = db()
        conn0.execute("DELETE FROM access WHERE base_id = ?", (old_sb['base_id'],))
        conn0.execute("DELETE FROM bases WHERE id = ?", (old_sb['base_id'],))
        conn0.execute("UPDATE sandboxes SET status = 'deleted', error = 'заменена новой' WHERE id = ?",
                      (old_sb['id'],))
        conn0.commit()
        audit('sandbox_replace', old_sb['slug'])

    dump = (request.form.get('dump') or '').strip()
    # S-04: только копии этой базы, строгое имя файла и путь внутри архива
    import re as _re
    allowed = {c['path'] for c in _sandbox_copies(row['db_name'] or row['slug'])}
    dbn = row['db_name'] or row['slug']
    ok_name = bool(_re.match(r'^%s-\d{8}-\d{4}\.dump$' % _re.escape(dbn), os.path.basename(dump)))
    ok_path = os.path.realpath(dump).startswith(os.path.realpath(SANDBOX_DIR) + os.sep)
    if not (ok_name and ok_path and dump in allowed):
        audit('sandbox_dump_denied', '%s: %s' % (row['slug'], dump[:120]))
        flash('Копия не найдена')
        return redirect('/')

    free = _sandbox_free_gb()
    min_free = float(_setting_get('sandbox_min_free_gb') or 8)
    need = os.path.getsize(dump) / 1024 ** 3 * 1.8
    if free - need < min_free:
        flash('Недостаточно места: свободно %.1f ГБ, нужно %.1f ГБ' % (free, need + min_free))
        return redirect('/')

    keep = int(_setting_get('sandbox_keep_days') or 3)
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    expires = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + keep * 86400))
    slug = 'sb_%s_%s' % (row['slug'], time.strftime('%m%d%H%M'))
    slug = slug[:32]

    conn = db()
    conn.execute("INSERT INTO bases (slug, title, organization, description, url_path, db_name, "
                 "is_active, is_sandbox, sandbox_of, sort_order) VALUES (?,?,?,?,?,?,1,1,?,99)",
                 (slug, 'Копия от %s (песочница)' % time.strftime('%d.%m'),
                  row['organization'] or '', 'Восстановленная копия базы %s' % row['slug'],
                  '/WEB/%s/' % slug, slug, row['slug']))
    new_bid = conn.execute("SELECT id FROM bases WHERE slug = ?", (slug,)).fetchone()['id']
    conn.execute("INSERT INTO access (user_id, base_id) VALUES (?,?)", (session['uid'], new_bid))
    sid = conn.execute(
        "INSERT INTO sandboxes (user_id, base_id, source_slug, source_db, slug, dump_path, dump_date, "
        "keep_days, created_at, expires_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,'creating')",
        (session['uid'], new_bid, row['slug'], row['db_name'] or row['slug'], slug, dump,
         time.strftime('%d.%m.%Y %H:%M'), keep, now, expires)).lastrowid
    conn.commit()

    audit('sandbox_create', '%s → %s' % (row['slug'], slug))
    jid, _ = _sandbox_run_job(sid, row['db_name'] or row['slug'], slug, dump)
    flash('Копия создаётся (задание №%s). Прогресс — в разделе «Задания», 10–20 минут.' % jid)
    return redirect('/')


@app.route('/sandbox/<int:sid>/delete', methods=['POST'])
@app.route('/admin/sandbox/<int:sid>/delete', methods=['POST'])
@login_required
def sandbox_delete(sid):
    check_csrf()
    row = db().execute("SELECT * FROM sandboxes WHERE id = ?", (sid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin' and row['user_id'] != session['uid']:
        abort(403)
    slug = row['slug']
    base_id = row['base_id']

    def done(code, path):
        conn = db()
        try:
            if code == 0:
                conn.execute("DELETE FROM access WHERE base_id = ?", (base_id,))
                conn.execute("DELETE FROM bases WHERE id = ?", (base_id,))
                conn.execute("UPDATE sandboxes SET status = 'deleted' WHERE id = ?", (sid,))
                conn.commit()
                audit('sandbox_delete', slug)
                _mm_notify('### Песочница удалена\n\n%s' % slug)
            else:
                tail = ''
                try:
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        tail = ' | '.join(f.read().splitlines()[-2:])[:200]
                except OSError:
                    pass
                conn.execute("UPDATE sandboxes SET error = ? WHERE id = ?", (tail, sid))
                conn.commit()
                audit('sandbox_delete_failed', '%s: %s' % (slug, tail))
        finally:
            conn.close()

    jid, _ = _job_start('sandbox-drop', 'Удаление песочницы %s' % slug,
                        ['/usr/local/bin/1c-sandbox', 'drop', slug], ref=str(sid), on_done=done)
    flash('Удаление песочницы «%s» запущено (задание №%s). Прогресс — в «Заданиях».' % (slug, jid))
    if session.get('role') == 'admin':
        return redirect(url_for('admin', tab='bases'))
    return redirect('/')



@app.route('/admin/users/<int:uid>/2fa/reset', methods=['POST'])
@admin_required
def admin_user_2fa_reset(uid):
    check_csrf()
    row = db().execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        abort(404)
    conn = db()
    conn.execute("UPDATE users SET totp_enabled = 0, totp_secret = NULL, totp_backup = NULL WHERE id = ?", (uid,))
    conn.commit()
    _trusted_drop(uid)
    audit('2fa_reset_by_admin', row['username'])
    flash('2FA у клиента %s сброшен' % row['username'])
    return redirect(url_for('admin', tab='users'))



# ===== управление кластером 1С =====

RAC_BIN = '/opt/1cv8/x86_64/8.3.27.2342/rac'


def _rac(args, timeout=60):
    """Вызов rac с правами администратора кластера из настроек."""
    login = _setting_get('cluster_user') or 'arshin'
    pwd = _setting_get('cluster_pwd') or ''
    cluster = _setting_get('cluster_uuid') or 'e3220a07-7374-4fc0-b4fb-25ace3789930'
    cmd = [RAC_BIN, '127.0.0.1:1545'] + list(args) + [
        '--cluster=%s' % cluster, '--cluster-user=%s' % login, '--cluster-pwd=%s' % pwd]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or '') + (proc.stderr or '')
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _rac_infobases():
    """Список инфобаз кластера: uuid, name, descr, db-name."""
    rc, out = _rac(['infobase', 'summary', 'list'])
    items = []
    cur = {}
    for line in (out or '').splitlines():
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key, val = key.strip(), val.strip().strip('"')
        if key == 'infobase':
            if cur.get('uuid'):
                items.append(cur)
            cur = {'uuid': val}
        elif key == 'name':
            cur['name'] = val
        elif key == 'descr':
            cur['descr'] = val
    if cur.get('uuid'):
        items.append(cur)
    return items


@app.route('/admin/cluster')
@admin_required
def admin_cluster():
    rc, raw = _rac(['infobase', 'summary', 'list'])
    return render_template('cluster.html', items=_rac_infobases(), raw=(raw or '')[:2000],
                           rc=rc, cluster_user=(_setting_get('cluster_user') or ''))


@app.route('/admin/cluster/create', methods=['POST'])
@admin_required
def admin_cluster_create():
    check_csrf()
    name = (request.form.get('name') or '').strip()
    db_name = (request.form.get('db_name') or name).strip()
    db_user = (request.form.get('db_user') or '').strip()
    db_pwd = request.form.get('db_pwd') or ''
    if not name or not db_user or not db_pwd:
        flash('Заполните имя инфобазы, пользователя и пароль PostgreSQL')
        return redirect(url_for('admin_cluster'))
    rc, out = _rac(['infobase', 'create', '--name=%s' % name, '--dbms=PostgreSQL',
                    '--db-server=127.0.0.1', '--db-name=%s' % db_name,
                    '--db-user=%s' % db_user, '--db-pwd=%s' % db_pwd,
                    '--locale=ru_RU', '--license-distribution=allow'], timeout=120)
    audit('cluster_create', '%s → %s' % (name, 'ok' if rc == 0 else out.strip()[:120]))
    flash('Инфобаза %s создана' % name if rc == 0 else 'Не удалось создать: %s' % out.strip()[:200])
    return redirect(url_for('admin_cluster'))


@app.route('/admin/cluster/<uuid>/drop', methods=['POST'])
@admin_required
def admin_cluster_drop(uuid):
    check_csrf()
    rc, out = _rac(['infobase', 'drop', '--infobase=%s' % uuid])
    audit('cluster_drop', '%s → %s' % (uuid, 'ok' if rc == 0 else out.strip()[:120]))
    flash('Инфобаза удалена' if rc == 0 else 'Не удалось удалить: %s' % out.strip()[:200])
    return redirect(url_for('admin_cluster'))


@app.route('/admin/cluster/<uuid>/rename', methods=['POST'])
@admin_required
def admin_cluster_rename(uuid):
    check_csrf()
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Укажите новое имя')
        return redirect(url_for('admin_cluster'))
    rc, out = _rac(['infobase', 'update', '--infobase=%s' % uuid, '--name=%s' % name])
    audit('cluster_rename', '%s → %s (%s)' % (uuid, name, 'ok' if rc == 0 else out.strip()[:120]))
    flash('Инфобаза переименована в %s' % name if rc == 0 else 'Не удалось переименовать: %s' % out.strip()[:200])
    return redirect(url_for('admin_cluster'))


@app.route('/admin/cluster/<uuid>/sessions', methods=['POST'])
@admin_required
def admin_cluster_sessions(uuid):
    check_csrf()
    deny = request.form.get('deny') == '1'
    rc, out = _rac(['infobase', 'update', '--infobase=%s' % uuid,
                    '--sessions-deny=%s' % ('true' if deny else 'false')])
    audit('cluster_sessions', '%s deny=%s' % (uuid, deny))
    flash('Сеансы %s' % ('запрещены' if deny else 'разрешены') if rc == 0 else 'Ошибка: %s' % out.strip()[:200])
    return redirect(url_for('admin_cluster'))


@app.route('/admin/cluster/settings', methods=['POST'])
@admin_required
def admin_cluster_settings():
    check_csrf()
    for key in ('cluster_user', 'cluster_pwd', 'cluster_uuid'):
        val = (request.form.get(key) or '').strip()
        if val:
            _setting_set(key, val)
    audit('cluster_settings', 'обновлены параметры доступа к кластеру')
    flash('Параметры кластера сохранены')
    return redirect(url_for('admin_cluster'))


@app.route('/admin/settings/sandbox', methods=['POST'])
@admin_required
def admin_settings_sandbox():
    check_csrf()
    keep = (request.form.get('sandbox_keep_days') or '3').strip()
    keep = keep if keep.isdigit() and 1 <= int(keep) <= 14 else '3'
    max_active = (request.form.get('sandbox_max_active') or '1').strip()
    max_active = max_active if max_active.isdigit() and 1 <= int(max_active) <= 5 else '1'
    min_free = (request.form.get('sandbox_min_free_gb') or '8').strip()
    min_free = min_free if min_free.isdigit() and 1 <= int(min_free) <= 200 else '8'

    _setting_set('sandbox_enabled', '1' if request.form.get('sandbox_enabled') else '0')
    _setting_set('sandbox_keep_days', keep)
    _setting_set('sandbox_max_active', max_active)
    _setting_set('sandbox_min_free_gb', min_free)
    _setting_set('sandbox_allow_transfer', '1' if request.form.get('sandbox_allow_transfer') else '0')
    _setting_set('sandbox_allow_extend', '1' if request.form.get('sandbox_allow_extend') else '0')
    _write_settings_json()
    _cache.clear()
    audit('settings_sandbox', 'keep=%s max=%s' % (keep, max_active))
    flash('Песочница: %s, хранение %s дн., лимит %s' % (
        'включена' if request.form.get('sandbox_enabled') else 'выключена', keep, max_active))
    return redirect(url_for('admin_settings'))



@app.route('/admin/sandbox/<int:sid>/transfer', methods=['POST'])
@admin_required
def sandbox_transfer(sid):
    """Передать песочницу другому клиенту."""
    check_csrf()
    if _setting_get('sandbox_allow_transfer') != '1':
        flash('Передача песочниц запрещена настройкой')
        return redirect(url_for('admin_settings'))

    row = db().execute("SELECT * FROM sandboxes WHERE id = ? AND status IN ('creating','ready')",
                       (sid,)).fetchone()
    if not row:
        flash('Песочница не найдена')
        return redirect(url_for('admin_settings'))

    target = (request.form.get('user_id') or '').strip()
    if not target.isdigit():
        flash('Выберите клиента, которому передаём песочницу')
        return redirect(url_for('admin_settings'))

    user = db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (int(target),)).fetchone()
    if not user:
        flash('Клиент не найден или заблокирован')
        return redirect(url_for('admin_settings'))
    if user['id'] == row['user_id']:
        flash('Песочница уже принадлежит этому клиенту')
        return redirect(url_for('admin_settings'))
    theirs = _sandbox_active(user['id'])
    if theirs:
        flash('У клиента %s уже есть песочница «%s» — сначала удалите её' % (user['username'], theirs[0]['slug']))
        return redirect(url_for('admin_settings'))

    conn = db()
    old = conn.execute("SELECT username FROM users WHERE id = ?", (row['user_id'],)).fetchone()
    if row['base_id']:
        conn.execute("DELETE FROM access WHERE base_id = ? AND user_id = ?",
                     (row['base_id'], row['user_id']))
        conn.execute("INSERT OR IGNORE INTO access (user_id, base_id) VALUES (?,?)",
                     (user['id'], row['base_id']))
    conn.execute("UPDATE sandboxes SET user_id = ? WHERE id = ?", (user['id'], sid))
    conn.commit()

    audit('sandbox_transfer', '%s: %s → %s' % (row['slug'], old['username'] if old else '?', user['username']))
    _mm_notify('### Песочница передана\n\n%s: %s → %s' % (
        row['slug'], old['username'] if old else '?', user['username']))
    flash('Песочница «%s» передана клиенту %s' % (row['slug'], user['username']))
    return redirect(url_for('admin_settings'))



@app.route('/admin/sandbox/<int:sid>/extend', methods=['POST'])
@admin_required
def sandbox_extend(sid):
    """Продлить песочницу на N дней."""
    check_csrf()
    if _setting_get('sandbox_allow_extend') != '1':
        flash('Продление песочниц запрещено настройкой')
        return redirect(url_for('admin', tab='bases'))
    row = db().execute("SELECT * FROM sandboxes WHERE id = ? AND status IN ('creating','ready')",
                       (sid,)).fetchone()
    if not row:
        flash('Песочница не найдена')
        return redirect(url_for('admin', tab='bases'))
    days = (request.form.get('days') or '').strip()
    if not days.isdigit() or not (1 <= int(days) <= 14):
        flash('Срок продления: от 1 до 14 дней')
        return redirect(url_for('admin', tab='bases'))
    expires = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + int(days) * 86400))
    db().execute("UPDATE sandboxes SET expires_at = ? WHERE id = ?", (expires, sid))
    db().commit()
    audit('sandbox_extend', '%s +%s дн.' % (row['slug'], days))
    flash('Песочница «%s» продлена до %s' % (row['slug'], expires[:16]))
    return redirect(url_for('admin', tab='bases'))



@app.route('/sandbox/<int:sid>/request-transfer', methods=['POST'])
@login_required
def sandbox_request_transfer(sid):
    """Клиент просит администратора передать песочницу другому человеку."""
    check_csrf()
    row = db().execute("SELECT * FROM sandboxes WHERE id = ? AND status IN ('creating','ready')",
                       (sid,)).fetchone()
    if not row:
        abort(404)
    if session.get('role') != 'admin' and row['user_id'] != session['uid']:
        abort(403)

    who = (request.form.get('to_name') or '').strip()
    org = (request.form.get('to_org') or '').strip()
    why = (request.form.get('reason') or '').strip()
    if len(who) < 2 or len(why) < 5:
        flash('Заполните: кому передать (ФИО) и причину передачи')
        return redirect('/')

    owner = db().execute("SELECT username, full_name, organization FROM users WHERE id = ?",
                         (row['user_id'],)).fetchone()
    base = db().execute("SELECT title FROM bases WHERE slug = ?", (row['source_slug'],)).fetchone()
    text = ('### Заявка на передачу песочницы\n\n'
            '**Песочница:** %s\n'
            '**База:** %s\n'
            '**Сейчас у:** %s (%s)%s\n'
            '**Передать:** %s%s\n'
            '**Причина:** %s\n'
            '**Время:** %s') % (
        row['slug'],
        (base['title'] if base else row['source_slug']),
        (owner['full_name'] or owner['username']) if owner else '?',
        owner['username'] if owner else '?',
        (' · ' + owner['organization']) if owner and owner['organization'] else '',
        who,
        (' · ' + org) if org else '',
        why,
        time.strftime('%d.%m.%Y %H:%M'))

    hook = _setting_get('monitor_hook') or ''
    sent = _mm_notify(text, hook=hook or None)
    audit('sandbox_request', '%s → %s' % (row['slug'], who))
    if sent:
        flash('Заявка отправлена администратору: %s' % who)
    else:
        flash('Заявка сохранена в журнале, но сообщение не ушло — сообщите администратору лично')
    return redirect('/')



# ===== длительные задания: прогресс, лог, «туман» =====

JOBS_LOG_DIR = '/var/log/1c-portal'


def _job_log(slug):
    return os.path.join(JOBS_LOG_DIR, slug + '.log')


def _job_start(kind, title, cmd, user_id=None, ref=None, on_done=None):
    """Запускает служебную команду в фоне, пишет лог и статус в jobs."""
    conn = db()
    # предыдущие задания того же вида считаем завершёнными с ошибкой (зависли или прерваны)
    try:
        conn.execute("UPDATE jobs SET status = 'failed', finished_at = ? WHERE kind = ? AND status = 'running'",
                     (time.strftime('%Y-%m-%d %H:%M:%S'), kind))
        conn.commit()
    except Exception:  # noqa: BLE001
        pass
    slug = '%s-%s' % (kind, time.strftime('%Y%m%d-%H%M%S'))
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    jid = conn.execute("INSERT INTO jobs (slug, kind, title, status, log_path, user_id, ref, created_at) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (slug, kind, title, 'running', _job_log(slug), user_id, ref, now)).lastrowid
    conn.commit()
    path = _job_log(slug)

    def work():
        with app.app_context():
            c2 = db()
            try:
                os.makedirs(JOBS_LOG_DIR, exist_ok=True)
                with open(path, 'w', encoding='utf-8', errors='replace') as out:
                    proc = subprocess.Popen(['sudo', '-n'] + cmd, stdout=out, stderr=subprocess.STDOUT,
                                            text=True, start_new_session=True)
                    code = proc.wait()
                c2.execute("UPDATE jobs SET status = ?, finished_at = ? WHERE id = ?",
                           ('done' if code == 0 else 'failed', time.strftime('%Y-%m-%d %H:%M:%S'), jid))
                c2.commit()
                if on_done is not None:
                    try:
                        on_done(code, path)
                    except Exception:  # noqa: BLE001
                        pass
                audit('job_' + kind, '%s: %s' % (slug, 'ok' if code == 0 else 'код %s' % code))
            except Exception as exc:  # noqa: BLE001
                try:
                    c2.execute("UPDATE jobs SET status = 'failed', finished_at = ? WHERE id = ?",
                               (time.strftime('%Y-%m-%d %H:%M:%S'), jid))
                    c2.commit()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    with open(path, 'a', encoding='utf-8') as out:
                        out.write('\nошибка запуска: %s\n' % exc)
                except OSError:
                    pass
            finally:
                c2.close()

    threading.Thread(target=work, daemon=True).start()
    return jid, slug


def _job_read(jid, tail=40):
    conn = db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not row:
        return None
    # статус не меняем на чтении: только показываем (обновление — на странице заданий)
    if row['status'] == 'running':
        try:
            age = time.time() - os.path.getmtime(row['log_path'])
        except OSError:
            age = 0
        if age > 900:
            row = dict(row)
            row['status'] = 'failed'
    lines = []
    try:
        with open(row['log_path'], 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()[-tail:]
    except OSError:
        pass
    size = 0
    try:
        size = os.path.getsize(row['log_path'])
    except OSError:
        pass
    percent, done, total = _job_progress(row['kind'], lines)
    return {'id': row['id'], 'slug': row['slug'], 'kind': row['kind'], 'title': row['title'],
            'status': row['status'], 'created_at': row['created_at'],
            'finished_at': row['finished_at'], 'log': lines, 'log_size': size,
            'percent': percent, 'done': done, 'total': total}



def _job_progress(kind, lines):
    """Простой прогресс: этапы «1/5» или число готовых баз."""
    import re as _re
    total, done = 0, 0
    for line in lines:
        m = _re.search(r'\[(\d+)/(\d+)\]', line)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
        elif ' ok ' in line or 'FAILED' in line or 'пропущена' in line:
            done += 1
            total = max(total, done)
    if kind == 'backup':
        total = max(total, 5)
    if total:
        return int(done * 100 / total), done, total
    return 0, 0, 0


@app.route('/jobs/<int:jid>/status')
@login_required
def job_status(jid):
    data = _job_read(jid)
    if not data:
        abort(404)
    # S-06: клиент видит только свои задания
    if session.get('role') != 'admin':
        row = db().execute("SELECT user_id FROM jobs WHERE id = ?", (jid,)).fetchone()
        if not row or row['user_id'] != session.get('uid'):
            abort(404)
    return data



@app.route('/jobs/active')
@login_required
def job_active():
    """Последнее выполняющееся задание — для индикатора в интерфейсе."""
    if session.get('role') == 'admin':
        row = db().execute("SELECT id FROM jobs WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
    else:
        # S-06: клиенту показываем только его задания
        row = db().execute("SELECT id FROM jobs WHERE status = 'running' AND user_id = ? "
                           "ORDER BY id DESC LIMIT 1", (session.get('uid'),)).fetchone()
    if not row:
        return {'active': False}
    data = _job_read(row['id'], tail=1)
    if not data:
        return {'active': False}
    return {'active': data['status'] == 'running', 'id': data['id'], 'title': data['title'],
            'percent': data['percent'], 'done': data['done'], 'total': data['total'],
            'admin': session.get('role') == 'admin'}


@app.route('/admin/jobs')
@admin_required
def admin_jobs():
    rows = db().execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 30").fetchall()
    current = None
    if rows:
        current = _job_read(rows[0]['id'], tail=80)
    return render_template('jobs.html', jobs=rows, current=current)


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORTAL_PORT', 8080)))
else:
    init_db()
    if os.environ.get('PORTAL_WARM') == '1':
        _start_warmer()
