#!/usr/bin/env python3
"""1C-AI-Control: логотип D в светлом стиле + набор иконок и эмодзи."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
LIGHT_DIR = os.path.join(ROOT, "light")
ICON_DIR = os.path.join(ROOT, "icons")
EMOJI_DIR = os.path.join(ROOT, "emoji")
for d in (LIGHT_DIR, ICON_DIR, EMOJI_DIR):
    os.makedirs(d, exist_ok=True)

PURPLE, PURPLE_D = "#7C5CFF", "#5B3FD1"
GREEN, GREEN_L = "#2FBF71", "#7BE0A7"
INK, INK2 = "#1B2436", "#5F6D85"
WHITE = "#FFFFFF"

# ---------- логотип D (светлый) ----------

def chip_mark(size=256, plate=True, label_color=WHITE):
    """Чип AI в светлом стиле: белая плита, фиолетовый чип, зелёная искра."""
    s = size / 256.0
    pins = """
    <g stroke="#C9D2E3" stroke-width="7" stroke-linecap="round">
      <path d="M78 78 v-20 M110 78 v-20 M146 78 v-20 M178 78 v-20"/>
      <path d="M78 178 v20 M110 178 v20 M146 178 v20 M178 178 v20"/>
      <path d="M78 78 h-20 M78 110 h-20 M78 146 h-20 M78 178 h-20"/>
      <path d="M178 78 h20 M178 110 h20 M178 146 h20 M178 178 h20"/>
    </g>"""
    plate_svg = ('<rect x="6" y="6" width="244" height="244" rx="58" fill="#F6F8FC" stroke="#DCE3F0" stroke-width="2"/>'
                 if plate else '')
    return f"""
  <g transform="scale({s})">
    {plate_svg}
    {pins}
    <rect x="78" y="78" width="100" height="100" rx="22" fill="url(#gPurple)"/>
    <text x="128" y="149" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
          font-size="52" font-weight="700" fill="{label_color}" letter-spacing="-2">AI</text>
    <circle cx="167" cy="89" r="7" fill="url(#gGreen)"/>
  </g>"""


DEFS = """  <defs>
    <linearGradient id="gPurple" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8E74FF"/><stop offset="1" stop-color="#5B3FD1"/>
    </linearGradient>
    <linearGradient id="gGreen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2FBF71"/><stop offset="1" stop-color="#7BE0A7"/>
    </linearGradient>
  </defs>"""


def svg(path, body, w, h):
    with open(os.path.join(ROOT, path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
                 + DEFS + body + "\n</svg>\n")
    print("  ", path)


# знак
svg("light/mark-d-chip-light.svg", chip_mark(256), 256, 256)

# горизонтальный
svg("light/logo-horizontal-light.svg", chip_mark(256) + """
  <text x="296" y="96" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="50" font-weight="700"
        fill="#1B2436" letter-spacing="-1">1C-AI-Control</text>
  <text x="298" y="134" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="21" fill="#5F6D85">
        копии · мониторинг · ИИ-проверки баз 1С</text>
  <rect x="298" y="150" width="94" height="4" rx="2" fill="url(#gGreen)"/>
""", 760, 256)

# вертикальный
svg("light/logo-stacked-light.svg", """
  <g transform="translate(82,44) scale(0.78)">""" + chip_mark(256).split("<g transform=\"scale(1.0)\">")[1].replace("</g>", "", 1) + """</g>
  <text x="210" y="300" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="40" font-weight="700" fill="#1B2436" letter-spacing="-1">1C-AI-Control</text>
  <text x="210" y="332" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="17" fill="#5F6D85">ИИ-контроль баз 1С</text>
""", 420, 380)

# ---------- иконки (24 px, штриховые, светлая тема) ----------
ICONS = {
    "dashboard": '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>',
    "database": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "sessions": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.2 6-5.2s6 1.9 6 5.2"/><path d="M16 5.5a3 3 0 0 1 0 5.9"/><path d="M17.5 20c0-2.4-1-4-2.5-4.9"/>',
    "backup": '<rect x="3" y="4" width="18" height="5" rx="2"/><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9"/><path d="M10 13h4"/>',
    "ai": '<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="2.2"/>',
    "shield": '<path d="M12 3l7.5 3v6c0 4.6-3.1 7.9-7.5 9-4.4-1.1-7.5-4.4-7.5-9V6z"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "users": '<circle cx="8.5" cy="8" r="3"/><path d="M2.5 19c0-3 2.7-4.8 6-4.8s6 1.8 6 4.8"/><circle cx="17" cy="9" r="2.5"/><path d="M15 14.4c2.8.2 4.8 1.7 4.8 4.1"/>',
    "cluster": '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M10.7 7.2 6.3 15.8M13.3 7.2l4.4 8.6M7.5 18h9"/>',
    "report": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M4.5 7.5l2 1.2M17.5 15.3l2 1.2M4.5 16.5l2-1.2M17.5 8.7l2-1.2"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/>',
    "warning": '<path d="M12 3.5 21 20H3z"/><path d="M12 9v5"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16.5 9"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.4 2"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/>',
    "lock": '<rect x="4.5" y="10" width="15" height="10.5" rx="2.5"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/>',
    "cloud": '<path d="M7 18a4.5 4.5 0 0 1-.4-9A5.5 5.5 0 0 1 17 8.6 3.7 3.7 0 0 1 17.5 18z"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7 9.5 10 12l-3 2.5M12.5 15H17"/>',
    "doc": '<path d="M6.5 3h7l4.5 4.5V21h-11.5z"/><path d="M13.5 3v4.5H18"/><path d="M9 13h6M9 16.5h6"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "plug": '<path d="M9 3v5M15 3v5"/><path d="M6.5 8h11v3.5a5.5 5.5 0 0 1-11 0z"/><path d="M12 17v4"/>',
    "sitemap": '<rect x="9" y="2.5" width="6" height="5" rx="1.5"/><rect x="2.5" y="16.5" width="6" height="5" rx="1.5"/><rect x="15.5" y="16.5" width="6" height="5" rx="1.5"/><path d="M12 7.5v4M5.5 16.5v-2h13v2"/>',
    "speed": '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4.5-5"/><circle cx="12" cy="18" r="1.4" fill="currentColor" stroke="none"/>',
}

for name, body in ICONS.items():
    with open(os.path.join(ICON_DIR, name + ".svg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
            'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round">\n  ' + body + "\n</svg>\n")
print("  иконки:", len(ICONS))

# ---------- эмодзи (72 px, цветные плашки) ----------
EMOJI = {
    "db": ("#7C5CFF", "#5B3FD1", '<ellipse cx="36" cy="26" rx="20" ry="7" fill="#fff" opacity=".95"/>'
                                '<path d="M16 26v16c0 4 9 7 20 7s20-3 20-7V26" fill="none" stroke="#fff" stroke-width="5"/>'),
    "ai": ("#8E74FF", "#5B3FD1", '<path d="M36 16l4 12 12 4-12 4-4 12-4-12-12-4 12-4z" fill="#fff"/>'),
    "backup": ("#2FBF71", "#1F9D5A", '<rect x="16" y="28" width="40" height="26" rx="6" fill="#fff"/>'
                                     '<path d="M24 22h12" stroke="#fff" stroke-width="5" stroke-linecap="round"/>'),
    "alert": ("#F5A623", "#D98600", '<path d="M36 16 56 52H16z" fill="#fff"/><path d="M36 30v12" stroke="#D98600" stroke-width="5" stroke-linecap="round"/>'),
    "ok": ("#2FBF71", "#1F9D5A", '<circle cx="36" cy="36" r="20" fill="#fff"/><path d="M27 37l6 6 12-13" stroke="#1F9D5A" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    "time": ("#5B6A85", "#3E4A61", '<circle cx="36" cy="36" r="20" fill="#fff"/><path d="M36 24v13l9 6" stroke="#3E4A61" stroke-width="5" fill="none" stroke-linecap="round"/>'),
    "users": ("#4C8DFF", "#2E6BD6", '<circle cx="29" cy="30" r="7" fill="#fff"/><circle cx="46" cy="32" r="5.5" fill="#fff" opacity=".85"/>'
                                     '<path d="M16 50c0-7 6-11 13-11s13 4 13 11" fill="#fff"/>'),
    "chart": ("#7C5CFF", "#5B3FD1", '<path d="M18 50V32M30 50V22M42 50V38M54 50V16" stroke="#fff" stroke-width="6" stroke-linecap="round"/>'),
    "lock": ("#5B6A85", "#3E4A61", '<rect x="20" y="32" width="32" height="24" rx="6" fill="#fff"/>'
                                   '<path d="M27 32v-6a9 9 0 0 1 18 0v6" stroke="#fff" stroke-width="5" fill="none"/>'),
    "cloud": ("#4C8DFF", "#2E6BD6", '<path d="M24 48a10 10 0 0 1-1-20 13 13 0 0 1 25 3 8 8 0 0 1 1 16z" fill="#fff"/>'),
    "gear": ("#7C5CFF", "#5B3FD1", '<circle cx="36" cy="36" r="9" fill="none" stroke="#fff" stroke-width="5"/>'
                                    '<path d="M36 16v6M36 50v6M16 36h6M50 36h6M22 22l4 4M46 46l4 4M22 50l4-4M46 26l4-4" stroke="#fff" stroke-width="5" stroke-linecap="round"/>'),
    "search": ("#5B6A85", "#3E4A61", '<circle cx="32" cy="32" r="12" fill="none" stroke="#fff" stroke-width="5"/>'
                                     '<path d="M41 41l10 10" stroke="#fff" stroke-width="6" stroke-linecap="round"/>'),
}

for name, (c1, c2, glyph) in EMOJI.items():
    body = (f'<defs><linearGradient id="eg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
            f'<rect x="2" y="2" width="68" height="68" rx="20" fill="url(#eg)"/>' + glyph)
    with open(os.path.join(EMOJI_DIR, name + ".svg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72" width="72" height="72">\n  '
                 + body + "\n</svg>\n")
print("  эмодзи:", len(EMOJI))
print("Готово")
