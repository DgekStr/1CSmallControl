#!/usr/bin/env python3
"""1C-AI-Control: финальные шаблоны — админ (вариант C, панельный), клиент (вариант B, минимал)."""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(ROOT, "templates")
os.makedirs(TPL, exist_ok=True)

ADMIN_NAV = ["Базы", "Сеансы", "Копии", "ИИ-проверки", "Мониторинг", "Пользователи"]
CLIENT_NAV = ["Мои базы", "ИИ-проверки", "Отчёты", "Копии", "Поддержка"]

BASE = """
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;line-height:1.55}
a{text-decoration:none}
.page{min-height:100vh;display:flex;flex-direction:column}
.content{flex:1;padding:44px 28px;max-width:1180px;margin:0 auto;width:100%}
h1{font-size:28px;margin:0 0 10px;letter-spacing:-.4px}
p.lead{font-size:15px;max-width:680px;margin:0 0 22px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.tile{border-radius:14px;padding:15px 17px;font-size:14px}
.tile b{display:block;margin-bottom:4px;font-size:15px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:4px 10px;border-radius:20px}
.dot{width:8px;height:8px;border-radius:50%;background:#2FBF71}
"""

DARK = """
:root{--ink:#E7EDF7;--mut:#9AAAC6;--line:rgba(255,255,255,.10);--panel:rgba(20,28,46,.72)}
body{background:#0D1320;color:var(--ink)}
.page{background:url('../backgrounds/bg-4-dark-deep.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(10,15,26,.74);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:24px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px}
.brand img{height:38px}
.nav{display:flex;gap:4px;flex-wrap:wrap}
.nav-link{padding:8px 13px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(255,255,255,.06)}
.nav-link.is-active{color:#fff;background:rgba(124,92,255,.24)}
.right{margin-left:auto;display:flex;align-items:center;gap:10px}
.chip{font-size:12.5px;padding:7px 12px;border-radius:10px;border:1px solid rgba(47,191,113,.3);background:rgba(47,191,113,.12);color:#7BE0A7}
.pill{font-size:13px;padding:7px 12px;border-radius:10px;border:1px solid var(--line);color:var(--mut)}
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
.f-bot{max-width:1180px;margin:0 auto;padding:12px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

LIGHT = """
:root{--ink:#1B2436;--mut:#5F6D85;--line:#DFE6F1;--panel:rgba(255,255,255,.86)}
body{background:#F6F8FC;color:var(--ink)}
.page{background:url('../backgrounds/bg-3-light-mesh.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(255,255,255,.8);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:24px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px}
.brand img{height:38px}
.nav{display:flex;gap:4px;flex-wrap:wrap}
.nav-link{padding:8px 13px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(91,63,209,.08)}
.nav-link.is-active{color:#fff;background:linear-gradient(135deg,#7C5CFF,#5B3FD1)}
.right{margin-left:auto;display:flex;align-items:center;gap:10px}
.chip{font-size:12.5px;padding:7px 12px;border-radius:10px;border:1px solid rgba(47,191,113,.32);background:rgba(47,191,113,.14);color:#1F9D5A}
.pill{font-size:13px;padding:7px 12px;border-radius:10px;border:1px solid var(--line);color:var(--mut);background:#fff}
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
.f-bot{max-width:1180px;margin:0 auto;padding:12px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

MINI = """
.mini-ftr{border-top:1px solid var(--line)}
.mini-ftr .in{max-width:1180px;margin:0 auto;padding:16px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.mini-links{display:flex;gap:16px;flex-wrap:wrap}
.mini-links a{font-size:12.5px;color:var(--mut)}
.mini-links a:hover{color:#7C5CFF}
.mini .nav-link{border-radius:999px;padding:7px 14px;font-size:13.5px}
.mini .hdr .in{padding:12px 28px}
"""


def nav(items, narrow=False):
    return "".join('<a class="nav-link%s" href="#">%s</a>' % (" is-active" if i == 0 else "", t)
                   for i, t in enumerate(items))


def header(items, right_html, narrow=False):
    return f"""
    <header class="hdr">
      <div class="in">
        <a class="brand" href="#"><img src="../light/mark-d-chip-light.svg" alt="">1C-AI-Control</a>
        <nav class="nav">{nav(items)}</nav>
        <div class="right">{right_html}</div>
      </div>
    </header>"""


def footer(brand_text, cols, note):
    cols_html = "".join(
        '<div class="f-col"><div class="f-title">%s</div>%s</div>'
        % (n, "".join('<a href="#">%s</a>' % i for i in items)) for n, items in cols)
    return f"""
    <footer class="ftr">
      <div class="in">
        <div class="f-brand">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <img src="../light/mark-d-chip-light.svg" alt="" style="height:34px;margin:0">
            <span style="font-weight:700;font-size:16px;color:var(--ink)">1C-AI-Control</span>
          </div>
          <div class="muted">{brand_text}</div>
          <div class="badge st" style="margin-top:12px"><span class="dot"></span>Все системы работают</div>
        </div>
        {cols_html}
      </div>
      <div class="f-bot">
        <span>© 2026 1C-AI-Control · v3.0.0</span>
        <span>{note}</span>
      </div>
    </footer>"""


def mini_footer(links):
    return """
    <footer class="ftr mini-ftr">
      <div class="in">
        <span style="font-weight:700">1C-AI-Control</span>
        <div class="mini-links">%s</div>
        <span style="font-size:12.5px;opacity:.75">© 2026 · v3.0.0</span>
      </div>
    </footer>""" % "".join('<a href="#">%s</a>' % l for l in links)


def page(theme, cls, title, h1, lead, tiles, hdr, ftr):
    css = BASE + (DARK if theme == "dark" else LIGHT) + MINI
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="page {cls}">
{hdr}
<main class="content">
  <span class="badge st"><span class="dot"></span>{'Панель администратора' if cls!='mini' else 'Кабинет клиента'} · демо</span>
  <h1>{h1}</h1>
  <p class="lead">{lead}</p>
  <div class="tiles">{tiles}</div>
</main>
{ftr}
</div></body></html>"""


ADMIN_TILES = """
<div class="tile"><b>Базы</b>4 базы · 1 286 сеансов за сутки</div>
<div class="tile"><b>Копии</b>сегодня 04:30 · успешно 5 / 0 ошибок</div>
<div class="tile"><b>ИИ-проверки</b>3 задачи · 12 находок</div>
<div class="tile"><b>Диск</b>IOPS 24 · свободно 241 ГБ из 469</div>"""

CLIENT_TILES = """
<div class="tile"><b>Бухгалтерия</b>1,7 ГБ · копия сегодня 04:30</div>
<div class="tile"><b>Зарплата</b>640 МБ · копия сегодня 04:31</div>
<div class="tile"><b>ИИ-проверка</b>5 задач сегодня · 12 находок</div>
<div class="tile"><b>Следующая копия</b>завтра 04:30</div>"""

ADMIN_COLS = [
    ("Продукт", ["Базы 1С", "Копии", "ИИ-проверки", "Мониторинг"]),
    ("Эксплуатация", ["Кластер", "Пользователи", "Лицензии", "Журнал"]),
    ("Поддержка", ["Инструкции", "Статус", "Контакты", "Заявка"]),
]
CLIENT_COLS = [
    ("Сервис", ["Мои базы", "ИИ-проверки", "Отчёты", "Копии"]),
    ("Помощь", ["Инструкции", "Поддержка", "Статус сервиса", "Обучение"]),
    ("О сервисе", ["Тарифы", "Оплата", "Договор и акты", "Контакты"]),
]

admin_right = ('<a class="view-switch" href="client-%s.html">Клиент →</a>'
               '<span class="pill">v3.0.0</span><a class="btn" href="#">Панель</a><span class="avatar">АК</span>')
client_right = ('<a class="view-switch" href="admin-%s.html">Админка →</a>'
                '<span class="chip">Тариф: Стандарт · 3 базы</span>'
                '<a class="btn" href="#">Заказать проверку</a><span class="avatar">ИП</span>')

# --- админ: вариант C (панельный) ---
for theme in ("dark", "light"):
    html = page(theme, "", "1C-AI-Control — панель администратора (%s)" % theme,
                "Панель администратора",
                "Вариант C · панельный: шапка с меню, плитки состояния, полный подвал.",
                ADMIN_TILES,
                header(ADMIN_NAV, admin_right % theme),
                footer("Копии, мониторинг и ИИ-проверки баз 1С. Работаем только с копией базы.",
                       ADMIN_COLS, "Политика · Условия · Поддержка 24/7"))
    name = "admin-%s.html" % theme
    io.open(os.path.join(TPL, name), "w", encoding="utf-8", newline="\n").write(html)
    print("  ", name)

# --- клиент: вариант B (минимал) ---
for theme in ("light", "dark"):
    html = page(theme, "mini", "1C-AI-Control — кабинет клиента (%s)" % theme,
                "Ваши базы под контролем",
                "Вариант B · минимал: короткое меню, подвал в одну строку.",
                CLIENT_TILES,
                header(CLIENT_NAV, client_right % theme, narrow=True),
                mini_footer(["Тарифы", "Оплата", "Документы", "Статус", "Поддержка"]))
    name = "client-%s.html" % theme
    io.open(os.path.join(TPL, name), "w", encoding="utf-8", newline="\n").write(html)
    print("  ", name)

print("Готово: финальные шаблоны")
