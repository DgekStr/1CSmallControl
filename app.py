"""Портал доступа к базам 1С: клиентский вход + админка."""
import http.client
import os
import re
import sqlite3
import secrets
import subprocess
import threading
import time

import maintenance
import metrics
from functools import wraps

from flask import (Flask, g, redirect, render_template, request, session,
                   url_for, abort, flash, Response)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('PORTAL_DB', os.path.join(BASE_DIR, 'portal.db'))

# Имя сервера 1С, которое показывается клиентам в инструкции по Конфигуратору.
IC_HOST = os.environ.get('PORTAL_IC_HOST', '1c.example.ru')
# Контакты сопровождения (блок «Нужна помощь с платформой?»).
SUPPORT_URL = os.environ.get('PORTAL_SUPPORT_URL', 'https://example.ru/contacts.html')
SUPPORT_NAME = os.environ.get('PORTAL_SUPPORT_NAME', 'example.ru')
# Версия портала — выводится в шапке и подвале.
APP_VERSION = os.environ.get('PORTAL_VERSION', '1.7')

app = Flask(__name__)
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
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
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
    try:
        db().execute("INSERT INTO audit(actor, action, details) VALUES(?,?,?)",
                     (session.get('user', 'anonymous'), action, details))
        db().commit()
    except Exception:
        pass


def _client_ip():
    """Реальный IP клиента: портал стоит за Apache, тот передаёт X-Forwarded-For."""
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr or ''


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


@app.route('/')
def index():
    if not session.get('uid'):
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin'))
    rows = db().execute("""
        SELECT b.* FROM bases b
        JOIN access a ON a.base_id = b.id
        WHERE a.user_id = ? AND b.is_active = 1
        ORDER BY b.sort_order, b.title""", (session['uid'],)).fetchall()
    jobs = {}
    if rows:
        slugs = tuple(b['slug'] for b in rows)
        info = _cached('counts:' + ','.join(slugs), 60,
                       lambda: _session_counts(list(slugs)))
        jobs = {k: v.get('jobs', 'off') for k, v in info.items()}
    pg_mode = _pg_mode_state()
    return render_template('portal.html', bases=rows, jobs=jobs, pg_mode=pg_mode,
                           maint=maintenance.state())


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
    return redirect('/WEB/%s/' % slug)


@app.route('/WEB/<slug>/', defaults={'rest': ''}, methods=WEB_METHODS)
@app.route('/WEB/<slug>/<path:rest>', methods=WEB_METHODS)
@login_required
def web_gate(slug, rest=''):
    base = db().execute("SELECT * FROM bases WHERE slug = ? AND is_active = 1", (slug,)).fetchone()
    if not base:
        abort(404)
    if session.get('role') != 'admin':
        allowed = db().execute("SELECT 1 FROM access WHERE user_id = ? AND base_id = ?",
                               (session['uid'], base['id'])).fetchone()
        if not allowed:
            audit('web_denied', slug)
            abort(403)

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
        return Response('1С недоступна: %s' % exc, status=502, mimetype='text/plain; charset=utf-8')
    return out


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and maintenance.blocking() and request.args.get('admin') != '1':
        return render_template('maintenance.html', st=maintenance.state())
    error = None
    if request.method == 'POST':
        check_csrf()
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        row = db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and row['is_active'] and check_password_hash(row['pass_hash'], password):
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
            audit('login', _client_ip())
            nxt = request.args.get('next') or '/'
            return redirect(nxt if nxt.startswith('/') else '/')
        error = 'Неверный логин или пароль'
        audit('login_failed', username)
    return render_template('login.html', error=error)


@app.route('/logout', methods=['POST'])
def logout():
    audit('logout', session.get('user', ''))
    if session.get('visit'):
        db().execute("UPDATE visits SET ended_at = datetime('now','localtime') WHERE id = ? AND ended_at IS NULL",
                     (session['visit'],))
        db().commit()
    session.clear()
    return redirect(url_for('login'))


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
    return redirect(row['url_path'])


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
            time.sleep(45)

    threading.Thread(target=loop, daemon=True).start()


@app.route('/admin')
@admin_required
def admin():
    users = db().execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    bases = db().execute("SELECT * FROM bases ORDER BY sort_order, title").fetchall()
    links = {(r['user_id'], r['base_id']) for r in db().execute("SELECT * FROM access")}
    tab = request.args.get('tab', 'users')
    if tab == 'stats':
        # статистика живёт на отдельном маршруте — иначе не хватает её данных
        return redirect(url_for('admin_stats'))
    counts = {}
    if tab == 'bases' and bases:
        _sync_cluster_state(bases)
        slugs = tuple(b['slug'] for b in bases)
        counts = _cached('counts:' + ','.join(slugs), 60,
                         lambda: _session_counts(list(slugs)))
    pg_mode = _pg_mode_state() if tab == 'bases' else 'off'
    return render_template('admin.html', users=users, bases=bases, links=links, tab=tab,
                           sessions=counts, pg_mode=pg_mode, maint=maintenance.state(),
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
    elif action == 'rename':
        name = (request.form.get('full_name') or '').strip()
        org = (request.form.get('organization') or '').strip()
        db().execute("UPDATE users SET full_name = ?, organization = ? WHERE id = ?", (name, org, uid))
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
        db().execute("UPDATE bases SET title=?, organization=?, description=?, url_path=?, db_name=? WHERE id=?",
                     (title, org, descr, url_path, db_name, bid))
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

    actual = _cached('basestate:' + ','.join(names), 60, fetch)
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
    return redirect(url_for('index'))


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
    done = []
    for row in bases:
        try:
            proc = subprocess.run(['sudo', '-n', '/usr/local/bin/1c-kick-sessions', row['slug']],
                                  capture_output=True, text=True, timeout=120)
            out = (proc.stdout or proc.stderr or '').strip().splitlines()
            if out:
                done.append('%s: %s' % (row['slug'], out[-1]))
        except Exception as exc:  # noqa: BLE001
            done.append('%s: ошибка %s' % (row['slug'], exc))
    for line in done:
        flash(line)
    if not done:
        flash('Нет активных баз для отключения')
    _cache.clear()
    audit('stats_kick', 'отключены все пользователи')
    return redirect(url_for('admin_stats'))



DEFAULT_SETTINGS = {
    'ic_host': os.environ.get('PORTAL_IC_HOST', '1c.dgek.ru'),
    'portal_server_name': os.environ.get('PORTAL_SERVER_NAME', '1c.dgek.ru'),
    'db_host': '127.0.0.1',
    'db_port': '5432',
    'db_user': 'postgres',
    'pg_admin_user': 'postgres',
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
    settings = _settings_all()
    host = settings.get('ic_host') or 'localhost'
    ref = row['db_name'] or row['slug']
    text = ('[Соединение с сервером 1С:Предприятие]\r\n'
            'Connect=Srvr="%s";Ref="%s";\r\n' % (host, ref))
    data = text.encode('cp1251', 'replace')
    audit('base_v8i', row['slug'])
    return Response(data, mimetype='application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="%s.v8i"' % row['slug'],
    })


@app.route('/healthz')


def healthz():
    return 'ok', 200


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORTAL_PORT', 8080)))
else:
    init_db()
    if os.environ.get('PORTAL_WARM') == '1':
        _start_warmer()
