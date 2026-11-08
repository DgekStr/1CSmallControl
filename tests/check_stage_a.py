"""Проверки этапа A (без pytest). Запуск: python check_stage_a.py"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

FAILED = []


def check(name, cond, extra=''):
    print(('  OK   ' if cond else '  FAIL ') + name + ((' — ' + extra) if extra and not cond else ''))
    if not cond:
        FAILED.append(name)


def main():
    from app import app, _safe_next

    app.config['TESTING'] = True

    with app.test_client() as c:
        with c.session_transaction() as s:
            s['uid'] = 1
            s['user'] = 'admin'
            s['role'] = 'admin'
            s['name'] = 'A'
            s['csrf'] = 't'
        for path in ('/WEB/demo/../test/', '/WEB/demo/..%2Ftest/',
                     '/WEB/demo/%2e%2e/test/', '/WEB/demo/%2f..%2ftest/'):
            r = c.get(path, follow_redirects=True)
            check('S-08 %s → 404' % path, r.status_code == 404, 'получили %s' % r.status_code)
        r = c.get('/WEB/demo/ru_RU/')
        check('S-08 нормальный путь не отклонён', r.status_code != 400, 'получили %s' % r.status_code)

    for bad in ('https://evil.example/', '//evil.example/', '\\\\evil', 'http:/x'):
        check('S-07 reject %r' % bad, _safe_next(bad) == '/', 'вернул %r' % _safe_next(bad))
    for good in ('/admin', '/?tab=1'):
        check('S-07 allow %r' % good, _safe_next(good) == good, 'вернул %r' % _safe_next(good))

    db = sqlite3.connect(os.environ.get('PORTAL_DB', 'portal.db'))
    db.row_factory = sqlite3.Row
    base = db.execute("select * from bases where slug='test' and coalesce(is_sandbox,0)=0").fetchone()
    user = db.execute("select id from users where username='test'").fetchone()
    if base and user:
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['uid'] = user['id']
                s['user'] = 'test'
                s['role'] = 'client'
                s['name'] = 'test'
                s['csrf'] = 't'
            r = c.post('/bases/%d/sandbox' % base['id'],
                       data={'csrf': 't', 'dump': '/mnt/1cbackup/dgek-20260101-0000.dump'},
                       follow_redirects=True)
            check('S-04 чужой дамп отклонён', 'Копия не найдена' in r.get_data(as_text=True))

    print()
    if FAILED:
        print('ПРОВАЛЕНО: %d' % len(FAILED))
        return 1
    print('ВСЁ ЗЕЛЁНОЕ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
