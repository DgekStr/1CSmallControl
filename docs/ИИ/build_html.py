import io, os, re, html

ROOT = r"E:\_Project\1CSmallControl\docs\ИИ"

CSS = """
:root{--bg:#0b1220;--panel:#111b2e;--line:#1f2d47;--text:#e6edf7;--muted:#93a4bf;--acc:#4f9cf9;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 22px 80px}
header.top{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:26px}
header.top h1{margin:0 0 6px;font-size:26px}
header.top .sub{color:var(--muted);font-size:13px}
nav.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 26px}
nav.tabs a{color:var(--text);text-decoration:none;border:1px solid var(--line);background:var(--panel);padding:8px 14px;border-radius:10px;font-size:13px}
nav.tabs a.active{border-color:var(--acc);color:#fff;background:#163055}
h1,h2,h3{line-height:1.25}
h2{margin:34px 0 12px;font-size:21px;border-bottom:1px solid var(--line);padding-bottom:8px}
h3{margin:24px 0 8px;font-size:17px;color:#cfe0ff}
p{margin:10px 0}
a{color:var(--acc)}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px;background:var(--panel);border-radius:10px;overflow:hidden}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:#16233a;font-weight:600}
tr:nth-child(even) td{background:#0f1828}
code{background:#0a1220;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:13px}
pre{background:#0a1220;border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto;font-size:13px}
pre code{border:0;background:none;padding:0}
blockquote{margin:14px 0;padding:10px 16px;border-left:3px solid var(--acc);background:#0f1a2c;color:var(--muted)}
ul,ol{margin:10px 0 10px 22px}
li{margin:4px 0}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}
footer{margin-top:48px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
"""

TABS = [("README.md", "Правила", "index.html"),
        ("roadmap.md", "Дорожная карта", "roadmap.html"),
        ("prompts-mcp.md", "Задания для MCP", "prompts-mcp.html"),
        ("tz-section.md", "Раздел ТЗ", "tz-section.html"),
        ("detectors.md", "Детекторы", "detectors.html"),
        ("decisions.md", "Решения", "decisions.html")]


def inline(t):
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def md_to_html(md):
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j, buf = i + 1, []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf)))
            i = j + 1; continue
        if re.match(r"^\s*\|", ln) and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            j = i + 2; rows = []
            while j < len(lines) and re.match(r"^\s*\|", lines[j]):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")]); j += 1
            out.append("<table><thead><tr>" + "".join("<th>%s</th>" % inline(c) for c in head) + "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
            out.append("</tbody></table>")
            i = j; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1)); out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2)), lvl)); i += 1; continue
        if re.match(r"^\s*[-*]\s+", ln):
            out.append("<ul>")
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                out.append("<li>%s</li>" % inline(re.sub(r"^\s*[-*]\s+", "", lines[i]))); i += 1
            out.append("</ul>"); continue
        if re.match(r"^\s*\d+\.\s+", ln):
            out.append("<ol>")
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                out.append("<li>%s</li>" % inline(re.sub(r"^\s*\d+\.\s+", "", lines[i]))); i += 1
            out.append("</ol>"); continue
        if ln.strip() == "---":
            out.append("<hr>"); i += 1; continue
        if ln.startswith(">"):
            out.append("<blockquote>%s</blockquote>" % inline(ln.lstrip("> "))); i += 1; continue
        if not ln.strip():
            i += 1; continue
        out.append("<p>%s</p>" % inline(ln)); i += 1
    return "\n".join(out)


def page(title, body, active):
    nav = "".join('<a href="%s" class="%s">%s</a>' % (f, "active" if f == active else "", t)
                  for _, t, f in TABS)
    return ("<!DOCTYPE html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>%s · ИИ-модуль 1C Small Control</title><style>%s</style></head><body><div class=\"wrap\">"
            "<header class=\"top\"><h1>ИИ-модуль портала 1C Small Control</h1>"
            "<div class=\"sub\">Правила работы · дорожная карта · задания для MCP · раздел ТЗ · v1.0 · 11.11.2026</div></header>"
            "<nav class=\"tabs\">%s</nav>%s"
            "<footer>Только песочницы · read-only · один ИИ-сеанс одновременно · версия портала 2.0.8</footer>"
            "</div></body></html>" % (html.escape(title), CSS, nav, body))


combined = []

for fname, tab_title, htmlname in TABS:
    path = os.path.join(ROOT, fname)
    md = io.open(path, encoding="utf-8").read()
    body = md_to_html(md)
    io.open(os.path.join(ROOT, htmlname), "w", encoding="utf-8", newline="\n").write(page(tab_title, body, htmlname))
    combined.append('<section id="%s"><h1 style="font-size:24px;margin-top:40px;color:#4f9cf9">%s</h1>%s</section><hr>' % (htmlname, tab_title, body))
    print("html:", htmlname)

io.open(os.path.join(ROOT, "all.html"), "w", encoding="utf-8", newline="\n").write(page("Все документы", "\n".join(combined), "all.html"))
print("html: all.html")
