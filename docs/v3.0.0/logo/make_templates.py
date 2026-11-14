#!/usr/bin/env python3
"""1C-AI-Control: шаблоны верхнего меню и подвала — 3 варианта × 2 фона."""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(ROOT, "templates")
os.makedirs(TPL, exist_ok=True)

NAV = [("Базы", "database"), ("Сеансы", "sessions"), ("Копии", "backup"),
       ("ИИ-проверки", "ai"), ("Мониторинг", "monitor"), ("Пользователи", "users")]


def nav_items(cls="nav-link", active="Базы"):
    return "\n".join(
        '<a class="%s%s" href="#">%s</a>' % (cls, " is-active" if t == active else "", t)
        for t, _ in NAV)


def footer_cols():
    cols = [
        ("Продукт", ["Базы 1С", "Резервные копии", "ИИ-проверки", "Мониторинг"]),
        ("Клиентам", ["Тарифы", "Подключение баз", "Перенос ККТ", "Обучение"]),
        ("Поддержка", ["Инструкции", "Статус сервиса", "Контакты", "Заявка в поддержку"]),
    ]
    return "\n".join(
        '<div class="f-col"><div class="f-title">%s</div>%s</div>'
        % (name, "".join('<a href="#">%s</a>' % i for i in items))
        for name, items in cols)


CSS_BASE = """
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;line-height:1.55}
a{text-decoration:none}
.page{min-height:100vh;display:flex;flex-direction:column}
.content{flex:1;padding:56px 28px;max-width:1180px;margin:0 auto;width:100%}
h1{font-size:30px;margin:0 0 10px}
p.lead{font-size:15px;max-width:640px;margin:0 0 26px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:8px}
.tile{border-radius:14px;padding:16px 18px;font-size:14px}
.tile b{display:block;margin-bottom:4px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:4px 10px;border-radius:20px}
.dot{width:8px;height:8px;border-radius:50%;background:#2FBF71}
"""

# ---------- тёмная тема ----------
CSS_DARK = """
:root{--ink:#E7EDF7;--mut:#9AAAC6;--line:rgba(255,255,255,.10);--panel:rgba(20,28,46,.72);--acc:#8E74FF;--acc2:#7C5CFF}
body{background:#0D1320;color:var(--ink)}
.page{background:url('../backgrounds/bg-4-dark-deep.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(10,15,26,.72);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:26px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px;letter-spacing:-.3px}
.brand img{height:38px}
.nav{display:flex;gap:4px;margin-left:8px;flex-wrap:wrap}
.nav-link{padding:8px 12px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(255,255,255,.06)}
.nav-link.is-active{color:#fff;background:rgba(124,92,255,.22)}
.hdr .right{margin-left:auto;display:flex;align-items:center;gap:10px}
.pill{font-size:13px;padding:7px 12px;border-radius:10px;border:1px solid var(--line);color:var(--mut)}
.btn{padding:9px 16px;border-radius:10px;background:linear-gradient(135deg,#8E74FF,#5B3FD1);color:#fff;font-size:14px;font-weight:600}
.avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#8E74FF,#2FBF71);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#0D1320}
.tile{background:var(--panel);border:1px solid var(--line)}
.f-status{background:rgba(47,191,113,.12);color:#7BE0A7;border:1px solid rgba(47,191,113,.25)}
.ftr{border-top:1px solid var(--line);background:rgba(10,15,26,.78);backdrop-filter:blur(14px)}
.ftr .in{max-width:1180px;margin:0 auto;padding:34px 28px 22px;display:grid;grid-template-columns:1.4fr repeat(3,1fr);gap:26px}
.f-brand img{height:36px;margin-bottom:10px}
.f-brand .muted{color:var(--mut);font-size:13px;max-width:280px}
.f-title{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin-bottom:10px}
.f-col a{display:block;color:#C7D2E8;font-size:13.5px;padding:3px 0}
.f-col a:hover{color:#fff}
.f-bot{max-width:1180px;margin:0 auto;padding:14px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

# ---------- светлая тема ----------
CSS_LIGHT = """
:root{--ink:#1B2436;--mut:#5F6D85;--line:#DFE6F1;--panel:rgba(255,255,255,.82);--acc:#5B3FD1}
body{background:#F6F8FC;color:var(--ink)}
.page{background:url('../backgrounds/bg-3-light-mesh.svg') center top / cover no-repeat fixed}
.hdr{position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);background:rgba(255,255,255,.78);border-bottom:1px solid var(--line)}
.hdr .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:26px;padding:14px 28px}
.brand{display:flex;align-items:center;gap:12px;color:var(--ink);font-weight:700;font-size:17px;letter-spacing:-.3px}
.brand img{height:38px}
.nav{display:flex;gap:4px;margin-left:8px;flex-wrap:wrap}
.nav-link{padding:8px 12px;border-radius:10px;color:var(--mut);font-size:14px}
.nav-link:hover{color:var(--ink);background:rgba(91,63,209,.08)}
.nav-link.is-active{color:#fff;background:linear-gradient(135deg,#7C5CFF,#5B3FD1)}
.hdr .right{margin-left:auto;display:flex;align-items:center;gap:10px}
.pill{font-size:13px;padding:7px 12px;border-radius:10px;border:1px solid var(--line);color:var(--mut);background:#fff}
.btn{padding:9px 16px;border-radius:10px;background:linear-gradient(135deg,#7C5CFF,#5B3FD1);color:#fff;font-size:14px;font-weight:600}
.avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#7C5CFF,#2FBF71);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff}
.tile{background:var(--panel);border:1px solid var(--line);box-shadow:0 1px 3px rgba(27,36,54,.06)}
.f-status{background:rgba(47,191,113,.14);color:#1F9D5A;border:1px solid rgba(47,191,113,.3)}
.ftr{border-top:1px solid var(--line);background:rgba(255,255,255,.86);backdrop-filter:blur(14px)}
.ftr .in{max-width:1180px;margin:0 auto;padding:34px 28px 22px;display:grid;grid-template-columns:1.4fr repeat(3,1fr);gap:26px}
.f-brand img{height:36px;margin-bottom:10px}
.f-brand .muted{color:var(--mut);font-size:13px;max-width:280px}
.f-title{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin-bottom:10px}
.f-col a{display:block;color:#26314A;font-size:13.5px;padding:3px 0}
.f-col a:hover{color:var(--acc)}
.f-bot{max-width:1180px;margin:0 auto;padding:14px 28px 26px;display:flex;justify-content:space-between;gap:14px;color:var(--mut);font-size:12.5px;flex-wrap:wrap}
"""

# ---------- вариант 2: минимал ----------
CSS_MIN = """
.hdr .in{padding:12px 28px;gap:18px}
.mini .nav{gap:2px}
.mini .nav-link{border-radius:999px;padding:7px 13px;font-size:13.5px}
.mini .hdr .in{border-bottom:none}
.mini-ftr{padding:18px 0}
.mini-ftr .in{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 28px;flex-wrap:wrap}
.mini-links{display:flex;gap:16px;flex-wrap:wrap}
.mini-links a{font-size:12.5px;color:var(--mut)}
.mini-links a:hover{color:var(--acc)}
"""


def variant_tiles():
    return """
      <div class="tiles">
        <div class="tile"><b>Базы</b>4 базы · 1 250 сеансов за сутки</div>
        <div class="tile"><b>Копии</b>последняя: сегодня 04:30 · успешно</div>
        <div class="tile"><b>ИИ-проверки</b>3 задачи сегодня · 12 находок</div>
        <div class="tile"><b>Мониторинг</b>IOPS 24 · диск 78 % · HASP ок</div>
      </div>"""


def header(variant="classic"):
    nav = nav_items("nav-link")
    right = ('<span class="pill">v3.0.0</span>'
             '<a class="btn" href="#">Открыть панель</a>'
             '<span class="avatar">АК</span>')
    return f"""
    <header class="hdr">
      <div class="in">
        <a class="brand" href="#"><img src="../light/mark-d-chip-light.svg" alt="">1C-AI-Control</a>
        <nav class="nav">{nav}</nav>
        <div class="right">{right}</div>
      </div>
    </header>"""


def footer(variant="classic"):
    return f"""
    <footer class="ftr">
      <div class="in">
        <div class="f-brand">
          <img src="../light/logo-horizontal-light.svg" alt="">
          <div class="muted">Копии, мониторинг и ИИ-проверки баз 1С. Работаем только с копией базы — данные не меняются.</div>
          <div class="badge f-status" style="margin-top:12px"><span class="dot"></span>Все системы работают</div>
        </div>
        {footer_cols()}
      </div>
      <div class="f-bot">
        <span>© 2026 1C-AI-Control · v3.0.0</span>
        <span>Политика конфиденциальности · Условия · Поддержка 24/7</span>
      </div>
    </footer>"""


def mini_footer():
    return """
    <footer class="ftr mini-ftr">
      <div class="in">
        <span style="font-weight:700">1C-AI-Control</span>
        <div class="mini-links">
          <a href="#">Тарифы</a><a href="#">Документы</a><a href="#">Статус</a><a href="#">Поддержка</a><a href="#">Контакты</a>
        </div>
        <span style="font-size:12.5px;opacity:.75">© 2026 · v3.0.0</span>
      </div>
    </footer>"""


def page(theme, title, extra_css, classic=True):
    css = CSS_BASE + (CSS_DARK if theme == "dark" else CSS_LIGHT) + CSS_MIN
    cls = "" if classic else "mini"
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="page {cls}">
{header()}
<main class="content">
  <span class="badge f-status"><span class="dot"></span>Демо шаблона · {theme} тема</span>
  <h1>Верхнее меню и подвал</h1>
  <p class="lead">Пример шапки и подвала в фирменном стиле: знак D, палитра, иконки. Ниже — плитки контента для проверки контраста на фоне.</p>
  {variant_tiles()}
</main>
{footer() if classic else mini_footer()}
</div></body></html>"""


def section(theme, title, html, note):
    return f"""
<section class="variant">
  <div class="v-title">{title}</div>
  <div class="v-note">{note}</div>
  <div class="v-frame">{html}</div>
</section>"""


def showcase(theme):
    css = CSS_BASE + (CSS_DARK if theme == "dark" else CSS_LIGHT) + CSS_MIN + """
.variant{margin:0 0 40px}
.v-title{font-size:16px;font-weight:700;margin:0 0 4px}
.v-note{font-size:13px;color:var(--mut);margin:0 0 12px}
.v-frame{border-radius:16px;overflow:hidden;border:1px solid var(--line)}
.wrap{max-width:1180px;margin:0 auto;padding:36px 24px 60px}
"""
    # каждый вариант — отдельный вложенный фрейм со своим фоном
    def frame(inner, variant_cls):
        return ('<div class="page %s" style="background-size:cover">' % variant_cls) + inner + '</div>'

    a = frame(header() + '<main class="content">' + variant_tiles() + '</main>' + footer(), "")
    b = frame(header() + '<main class="content">' + variant_tiles() + '</main>' + mini_footer(), "mini")
    c = frame(header() + '<main class="content">' + variant_tiles() + '</main>' + footer(), "")

    body = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>1C-AI-Control — меню и подвал ({'тёмная' if theme=='dark' else 'светлая'} тема)</title>
<style>{css}</style></head>
<body><div class="page" style="min-height:auto;background:url('../backgrounds/bg-{'4-dark-deep' if theme=='dark' else '3-light-mesh'}.svg') center top / cover no-repeat fixed">
<div class="wrap">
  <h1 style="margin-bottom:6px">Верхнее меню и подвал — {'тёмная' if theme=='dark' else 'светлая'} тема</h1>
  <p class="lead">Три варианта: классика с колонками, минимал в одну строку, и «панельный» с плитками. Фон: bg-{'4-dark-deep' if theme=='dark' else '3-light-mesh'}.svg</p>
  {section(theme, 'Вариант A · Классика', a, 'Логотип слева, меню по центру, кнопка и аватар справа. Подвал — 4 колонки + строка копирайта.')}
  {section(theme, 'Вариант B · Минимал', b, 'Пилюли-ссылки, подвал в одну строку. Хорош для внутренней панели, где важна плотность.')}
  {section(theme, 'Вариант C · Панельный', c, 'Тот же каркас, но с плитками-виджетами в контенте — проверка контраста на фоне.')}
</div>
</div></body></html>"""
    name = "header-footer-%s.html" % ("dark" if theme == "dark" else "light")
    io.open(os.path.join(TPL, name), "w", encoding="utf-8", newline="\n").write(body)
    print("  ", name, len(body), "байт")


showcase("dark")
showcase("light")
print("Готово: шаблоны")

# --- правка: фреймы по высоте контента ---
_p = os.path.join(TPL, "header-footer-dark.html")
for _f in ("header-footer-dark.html", "header-footer-light.html"):
    _p = os.path.join(TPL, _f)
    _s = io.open(_p, encoding="utf-8").read()
    _s = _s.replace(".v-frame{border-radius:16px;overflow:hidden;border:1px solid var(--line)}",
                    ".v-frame{border-radius:16px;overflow:hidden;border:1px solid var(--line)}\n"
                    ".v-frame .page{min-height:auto}\n.v-frame .content{padding:36px 24px}")
    io.open(_p, "w", encoding="utf-8", newline="\n").write(_s)
    print("  правка высоты:", _f)
