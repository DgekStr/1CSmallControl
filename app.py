"""Портал доступа к базам 1С: клиентский вход + админка."""
import os
import re
import sqlite3
import secrets
import time
from functools import wraps

from flask import (Flask, g, redirect, render_template, request, session,
                   url_for, abort, flash)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('PORTAL_DB', os.path.join(BASE_DIR, 'portal.db'))

app = Flask(__name__)
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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
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


def csrf_token():
    tok = session.get('csrf')
    if not tok:
        tok = secrets.token_urlsafe(32)
        session['csrf'] = tok
    return tok


app.jinja_env.globals['csrf_token'] = csrf_token


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
    return render_template('portal.html', bases=rows)


@app.route('/login', methods=['GET', 'POST'])
def login():
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
            audit('login', row['username'])
            nxt = request.args.get('next') or '/'
            return redirect(nxt if nxt.startswith('/') else '/')
        error = 'Неверный логин или пароль'
        audit('login_failed', username)
    return render_template('login.html', error=error)


@app.route('/logout', methods=['POST'])
def logout():
    audit('logout', session.get('user', ''))
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

@app.route('/admin')
@admin_required
def admin():
    users = db().execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    bases = db().execute("SELECT * FROM bases ORDER BY sort_order, title").fetchall()
    links = {(r['user_id'], r['base_id']) for r in db().execute("SELECT * FROM access")}
    return render_template('admin.html', users=users, bases=bases, links=links,
                           tab=request.args.get('tab', 'users'))


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
        db().execute("INSERT INTO bases(slug,title,organization,description,url_path) VALUES(?,?,?,?,?)",
                     (slug, title or slug, org, descr, url_path))
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
        db().execute("UPDATE bases SET title=?, organization=?, description=?, url_path=? WHERE id=?",
                     (title, org, descr, url_path, bid))
        db().commit()
        audit('base_edit', row['slug'])
        flash(f'База «{row["slug"]}» обновлена')
    return redirect(url_for('admin', tab='bases'))


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


@app.route('/healthz')
def healthz():
    return 'ok', 200


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORTAL_PORT', 8080)))
else:
    init_db()
