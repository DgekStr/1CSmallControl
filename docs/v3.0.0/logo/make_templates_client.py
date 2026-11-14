#!/usr/bin/env python3
"""1C-AI-Control: шаблоны шапки и подвала для КЛИЕНТСКОГО кабинета (2 темы)."""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(ROOT, "templates")
os.makedirs(TPL, exist_ok=True)

CLIENT_NAV = [("Мои базы", True), ("ИИ-проверки", False), ("Отчёты", False),
              ("Копии", False), ("Поддержка", False)]

CSS_BASE = """
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;line-height:1.55}
a{text-decoration:none}
.page{min-height:100vh;display:flex;flex-direction:column}
.content{flex:1;padding:48px 28px;max-width:1180px;margin:0 auto;width:100%}
h1{font-size:29px;margin:0 0 10px;letter-spacing:-.4px}
p.lead{font-size:15px;max-width:660px;margin:0 0 24px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.tile{border-radius:14px;padding:16px 18px;font-size:14px}
.tile b{display:block;margin-bottom:4px;font-size:15px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:4px 10px;border-radius:20px}
.dot{width:8px;height:8px;border-radius:50%;background:#2FBF71}
"""

CSS_DARK = """
:root{--ink:#E7EDF7;--mut:#9AAAC6;--line:rgba(255,255,255,.10);--panel:rgba(20,28,46,.72)}
body{background:#0D1320;color:var(--ink)}
.page{background:url('../backgrounds/bg-4-dark-deep.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(10,15,26,.74);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:24px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px}
.brand img{height:38px}
.nav{display:flex;gap:4px;margin-left:6px;flex-wrap:wrap}
.nav-link{padding:8px 13px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(255,255,255,.06)}
.nav-link.is-active{color:#fff;background:rgba(124,92,255,.24)}
.right{margin-left:auto;display:flex;align-items:center;gap:10px}
.chip{font-size:12.5px;padding:7px 12px;border-radius:10px;border:1px solid rgba(47,191,113,.3);background:rgba(47,191,113,.12);color:#7BE0A7}
.btn{padding:9px 16px;border-radius:10px;background:linear-gradient(135deg,#8E74FF,#5B3FD1);color:#fff;font-size:14px;font-weight:600}
.avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#8E74FF,#2FBF71);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#0D1320}
.tile{background:var(--panel);border:1px solid var(--line)}
.st{background:rgba(47,191,113,.12);color:#7BE0A7;border:1px solid rgba(47,191,113,.25)}
.ftr{border-top:1px solid var(--line);background:rgba(10,15,26,.8);backdrop-filter:blur(14px)}
.ftr .in{max-width:1180px;margin:0 auto;padding:32px 28px 20px;display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:26px}
.f-brand img{height:34px;margin-bottom:10px}
.f-brand .muted{color:var(--mut);font-size:13px;max-width:290px}
.f-title{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin-bottom:10px}
.f-col a{display:block;color:#C7D2E8;font-size:13.5px;padding:3px 0}
.f-col a:hover{color:#fff}
.f-bot{max-width:1180px;margin:0 auto;padding:12px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

CSS_LIGHT = """
:root{--ink:#1B2436;--mut:#5F6D85;--line:#DFE6F1;--panel:rgba(255,255,255,.86)}
body{background:#F6F8FC;color:var(--ink)}
.page{background:url('../backgrounds/bg-3-light-mesh.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(255,255,255,.8);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:24px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px}
.brand img{height:38px}
.nav{display:flex;gap:4px;margin-left:6px;flex-wrap:wrap}
.nav-link{padding:8px 13px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(91,63,209,.08)}
.nav-link.is-active{color:#fff;background:linear-gradient(135deg,#7C5CFF,#5B3FD1)}
.right{margin-left:auto;display:flex;align-items:center;gap:10px}
.chip{font-size:12.5px;padding:7px 12px;border-radius:10px;border:1px solid rgba(47,191,113,.32);background:rgba(47,191,113,.14);color:#1F9D5A}
.btn{padding:9px 16px;border-radius:10px;background:linear-gradient(135deg,#7C5CFF,#5B3FD1);color:#fff;font-size:14px;font-weight:600}
.avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#7C5CFF,#2FBF71);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff}
.tile{background:var(--panel);border:1px solid var(--line);box-shadow:0 1px 3px rgba(27,36,54,.06)}
.st{background:rgba(47,191,113,.14);color:#1F9D5A;border:1px solid rgba(47,191,113,.3)}
.ftr{border-top:1px solid var(--line);background:rgba(255,255,255,.88);backdrop-filter:blur(14px)}
.ftr .in{max-width:1180px;margin:0 auto;padding:32px 28px 20px;display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:26px}
.f-brand img{height:34px;margin-bottom:10px}
.f-brand .muted{color:var(--mut);font-size:13px;max-width:290px}
.f-title{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin-bottom:10px}
.f-col a{display:block;color:#26314A;font-size:13.5px;padding:3px 0}
.f-col a:hover{color:#5B3FD1}
.f-bot{max-width:1180px;margin:0 auto;padding:12px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

CSS_EXTRA = """
.variant{margin:0 0 38px}
.v-title{font-size:16px;font-weight:700;margin:0 0 4px}
.v-note{font-size:13px;color:var(--mut);margin:0 0 12px}
.v-frame{border-radius:16px;overflow:hidden;border:1px solid var(--line)}
.v-frame .page{min-height:auto}
.v-frame .content{padding:34px 24px}
.wrap{max-width:1180px;margin:0 auto;padding:34px 24px 56px}
.mini-ftr .in{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 28px;flex-wrap:wrap}
.mini-links{display:flex;gap:16px;flex-wrap:wrap}
.mini-links a{font-size:12.5px;color:var(--mut)}
.mini-links a:hover{color:#7C5CFF}
.slim .hdr .in{padding:11px 28px}
.slim .nav-link{border-radius:999px;padding:7px 14px;font-size:13.5px}
"""


def header():
    nav = "\n".join('<a class="nav-link%s" href="#">%s</a>' % (" is-active" if a else "", t)
                    for t, a in CLIENT_NAV)
    return f"""
    <header class="hdr">
      <div class="in">
        <a class="brand" href="#"><img src="../light/mark-d-chip-light.svg" alt="">1C-AI-Control</a>
        <nav class="nav">{nav}</nav>
        <div class="right">
          <span class="chip">Тариф: Стандарт · 3 базы</span>
          <a class="btn" href="#">Заказать проверку</a>
          <span class="avatar">ИП</span>
        </div>
      </div>
    </header>"""


def content():
    return """
    <main class="content">
      <span class="badge st"><span class="dot"></span>Кабинет клиента · демо</span>
      <h1>Ваши базы под контролем</h1>
      <p class="lead">Копии, мониторинг и ИИ-проверки — без доступа к рабочей базе. Ниже плитки для проверки читаемости.</p>
      <div class="tiles">
        <div class="tile"><b>Бухгалтерия</b>1,7 ГБ · копия сегодня 04:30</div>
        <div class="tile"><b>Зарплата</b>640 МБ · копия сегодня 04:31</div>
        <div class="tile"><b>ИИ-проверка</b>5 задач сегодня · 12 находок</div>
        <div class="tile"><b>Следующая копия</b>завтра 04:30</div>
      </div>
    </main>"""


def footer():
    cols = [
        ("Сервис", ["Мои базы", "ИИ-проверки", "Отчёты", "Копии"]),
        ("Помощь", ["Инструкции", "Поддержка", "Статус сервиса", "Обучение"]),
        ("О сервисе", ["Тарифы", "Оплата", "Договор и акты", "Контакты"]),
    ]
    cols_html = "\n".join(
        '<div class="f-col"><div class="f-title">%s</div>%s</div>'
        % (n, "".join('<a href="#">%s</a>' % i for i in items)) for n, items in cols)
    return f"""
    <footer class="ftr">
      <div class="in">
        <div class="f-brand">
          <img src="../light/logo-horizontal-light.svg" alt="">
          <div class="muted">Проверяем копию базы, а не рабочую. Персональные данные обезличиваются (152-ФЗ).</div>
          <div class="badge st" style="margin-top:12px"><span class="dot"></span>Все системы работают</div>
        </div>
        {cols_html}
      </div>
      <div class="f-bot">
        <span>© 2026 1C-AI-Control · v3.0.0</span>
        <span>Политика конфиденциальности · Договор · Поддержка 24/7</span>
      </div>
    </footer>"""


def mini_footer():
    return """
    <footer class="ftr mini-ftr">
      <div class="in">
        <span style="font-weight:700">1C-AI-Control</span>
        <div class="mini-links">
          <a href="#">Тарифы</a><a href="#">Оплата</a><a href="#">Документы</a><a href="#">Статус</a><a href="#">Поддержка</a>
        </div>
        <span style="font-size:12.5px;opacity:.75">© 2026 · v3.0.0</span>
      </div>
    </footer>"""


def build(theme):
    css = CSS_BASE + (CSS_DARK if theme == "dark" else CSS_LIGHT) + CSS_EXTRA
    bg = "4-dark-deep" if theme == "dark" else "3-light-mesh"
    a = '<div class="page">' + header() + content() + footer() + '</div>'
    b = '<div class="page slim">' + header() + content() + mini_footer() + '</div>'
    c = '<div class="page">' + header() + content() + footer() + '</div>'
    title = "тёмная" if theme == "dark" else "светлая"
    body = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>1C-AI-Control — клиентский кабинет ({title} тема)</title>
<style>{css}</style></head>
<body><div class="page" style="min-height:auto">
<div class="wrap">
  <h1 style="margin-bottom:6px">Шапка и подвал — клиентский кабинет ({title} тема)</h1>
  <p class="lead">Фон: bg-{bg}.svg. Меню клиента: Мои базы · ИИ-проверки · Отчёты · Копии · Поддержка. Справа — тариф, кнопка заказа проверки, аватар.</p>
  <div class="variant"><div class="v-title">Вариант A · Классика</div>
    <div class="v-note">Полноценный подвал с колонками «Сервис / Помощь / О сервисе» и статусом работы.</div>
    <div class="v-frame">{a}</div></div>
  <div class="variant"><div class="v-title">Вариант B · Минимал</div>
    <div class="v-note">Подвал в одну строку, пилюли в меню — для мобильных и плотных экранов.</div>
    <div class="v-frame">{b}</div></div>
  <div class="variant"><div class="v-title">Вариант C · Кабинет</div>
    <div class="v-note">Тот же каркас с плитками баз: видно, что копия свежая и ИИ-проверки идут.</div>
    <div class="v-frame">{c}</div></div>
</div>
</div></body></html>"""
    name = "header-footer-client-%s.html" % ("dark" if theme == "dark" else "light")
    io.open(os.path.join(TPL, name), "w", encoding="utf-8", newline="\n").write(body)
    print("  ", name, len(body), "байт")


build("dark")
build("light")
print("Готово: клиентские шаблоны")
