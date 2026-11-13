#!/usr/bin/env python3
"""Сборка HTML из markdown для docs/v3.0.0 (без внешних зависимостей)."""
import html
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

CSS = """
:root{--bg:#0f1420;--panel:#161d2e;--border:#263149;--text:#e7edf7;--muted:#93a4bf;--accent:#7c5cff;--ok:#2fbf71;--warn:#f5a623}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,Arial,sans-serif;line-height:1.6}
.wrap{max-width:980px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 8px}
h2{font-size:19px;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--border)}
h3{font-size:15px;margin:20px 0 8px}
p{margin:10px 0}
a{color:#b7a4ff}
table{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0;background:var(--panel);border-radius:10px;overflow:hidden}
th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
tr:last-child td{border-bottom:none}
code{background:rgba(124,92,255,.12);padding:1px 5px;border-radius:5px;font-family:Consolas,monospace;font-size:.92em}
pre{background:#101728;border:1px solid var(--border);border-radius:10px;padding:14px;overflow:auto}
pre code{background:none;padding:0}
blockquote{margin:14px 0;padding:10px 14px;border-left:3px solid var(--accent);background:rgba(124,92,255,.08);border-radius:8px}
ul,ol{margin:10px 0;padding-left:22px}
li{margin:4px 0}
.tag{display:inline-block;padding:2px 8px;border-radius:20px;font-size:12px;background:rgba(47,191,113,.15);color:var(--ok)}
"""


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def convert(md):
    out, i, lines = [], 0, md.split('\n')
    in_code = False
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            if in_code:
                out.append('</code></pre>')
                in_code = False
            else:
                out.append('<pre><code>')
                in_code = True
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue
        if re.match(r'^\|', line) and i + 1 < len(lines) and re.match(r'^\|[\s:\-|]+\|', lines[i + 1]):
            header = [c.strip() for c in line.strip().strip('|').split('|')]
            out.append('<table><thead><tr>' + ''.join('<th>%s</th>' % inline(c) for c in header) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                out.append('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in cells) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        m = re.match(r'^(#{1,3})\s+(.*)$', line)
        if m:
            lvl = len(m.group(1))
            out.append('<h%d>%s</h%d>' % (lvl, inline(m.group(2)), lvl))
        elif line.startswith('> '):
            out.append('<blockquote>%s</blockquote>' % inline(line[2:]))
        elif re.match(r'^\s*[-*]\s+', line):
            items = []
            while i < len(lines) and re.match(r'^\s*[-*]\s+', lines[i]):
                items.append('<li>%s</li>' % inline(re.sub(r'^\s*[-*]\s+', '', lines[i])))
                i += 1
            out.append('<ul>' + ''.join(items) + '</ul>')
            continue
        elif re.match(r'^\s*\d+\.\s+', line):
            items = []
            while i < len(lines) and re.match(r'^\s*\d+\.\s+', lines[i]):
                items.append('<li>%s</li>' % inline(re.sub(r'^\s*\d+\.\s+', '', lines[i])))
                i += 1
            out.append('<ol>' + ''.join(items) + '</ol>')
            continue
        elif line.strip():
            out.append('<p>%s</p>' % inline(line))
        i += 1
    if in_code:
        out.append('</code></pre>')
    return '\n'.join(out)


def build(name, md_path, title):
    md = open(md_path, encoding='utf-8').read()
    body = convert(md)
    page = ('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body><div class="wrap">%s</div></body></html>'
            % (html.escape(title), CSS, body))
    out = os.path.join(ROOT, name)
    open(out, 'w', encoding='utf-8', newline='\n').write(page)
    print('  ', name, len(page), 'байт')


FILES = [
    ('README.md', 'README.html', '1C-AI-Control v3.0.0 — документация'),
    ('prompt-cluster-service.md', 'prompt-cluster-service.html', 'Промпт: сервис управления кластером 1С'),
    ('prompt-ai-in-1c.md', 'prompt-ai-in-1c.html', 'Промпт: ИИ-модуль в 1С'),
    ('prompt-mcp.md', 'prompt-mcp.html', 'Промпт: MCP-сервер ИИ-модуля (системный промт и задания)'),
    ('unified-prompt.md', 'unified-prompt.html', '1C-AI-Control v3.0.0 — единый промпт и дорожная карта'),
]

if __name__ == '__main__':
    print('Сборка HTML:')
    for md, out, title in FILES:
        build(out, os.path.join(ROOT, md), title)
    # дорожная карта = отдельная копия единого промпта
    src = os.path.join(ROOT, 'unified-prompt.html')
    if os.path.exists(src):
        body = open(src, encoding='utf-8').read().replace(
            '1C-AI-Control v3.0.0 — единый промпт и дорожная карта',
            '1C-AI-Control v3.0.0 — дорожная карта (пошагово)')
        open(os.path.join(ROOT, 'roadmap.html'), 'w', encoding='utf-8', newline='\n').write(body)
        print('   roadmap.html')
