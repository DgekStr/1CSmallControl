#!/usr/bin/env python3
"""Генерация вариантов логотипа 1C-AI-Control v3.0.0 (SVG) — v2, улучшенные знаки."""
import os

OUT = os.path.dirname(os.path.abspath(__file__))
PURPLE_A = "#8E74FF"
PURPLE_B = "#5B3FD1"
GREEN = "#2FBF71"
GREEN_L = "#7BE0A7"

DEFS = """
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#242E4C"/><stop offset="1" stop-color="#0F1524"/>
    </linearGradient>
    <linearGradient id="acc" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8E74FF"/><stop offset="1" stop-color="#5B3FD1"/>
    </linearGradient>
    <linearGradient id="grn" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2FBF71"/><stop offset="1" stop-color="#7BE0A7"/>
    </linearGradient>
    <linearGradient id="pl" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#5B3FD1"/><stop offset="1" stop-color="#8E74FF"/>
    </linearGradient>
  </defs>
"""

# четырёхлучевая «искра» как символ ИИ
SPARK = "M 0 -22 Q 5 -5 22 0 Q 5 5 0 22 Q -5 5 -22 0 Q -5 -5 0 -22 Z"

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'


def save(name, body, w=256, h=256):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD.format(w=w, h=h) + "\n" + DEFS + body + "\n</svg>\n")
    print("  ", name)


# ---------- A. Монограмма 1C + искра ИИ ----------
save("mark-a-monogram.svg", """
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <rect x="8" y="8" width="240" height="240" rx="56" fill="none" stroke="#2E3A5A" stroke-width="2"/>
  <text x="34" y="170" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="104" font-weight="700"
        fill="#FFFFFF" letter-spacing="-5">1C</text>
  <g transform="translate(196,84)">
    <path d="{spark}" fill="url(#grn)"/>
  </g>
  <path d="M40 196 H150" stroke="#7C5CFF" stroke-width="8" stroke-linecap="round"/>
  <circle cx="176" cy="196" r="7" fill="#8E74FF"/>
""".replace("{spark}", SPARK))


# ---------- B. База + пульс (без пересечений) ----------
save("mark-b-pulse.svg", """
  <rect x="8" y="8" width="240" height="240" rx="56" fill="#FFFFFF" stroke="#D9E0EC" stroke-width="2"/>
  <g stroke="#7C5CFF" stroke-width="11" fill="none" stroke-linecap="round">
    <ellipse cx="128" cy="86" rx="52" ry="18"/>
    <path d="M76 86 v34 c0 10 23 18 52 18 s52 -8 52 -18 V86"/>
    <path d="M76 120 v34 c0 10 23 18 52 18 s52 -8 52 -18 v-34"/>
  </g>
  <path d="M56 200 H100 l14 -30 18 52 16 -38 h22" fill="none" stroke="url(#grn)" stroke-width="10"
        stroke-linecap="round" stroke-linejoin="round"/>
""")


# ---------- C. Щит + база ----------
save("mark-c-shield.svg", """
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <path d="M128 32 l66 26 v58 c0 46 -30 78 -66 94 c-36 -16 -66 -48 -66 -94 V58 Z"
        fill="none" stroke="url(#acc)" stroke-width="10" stroke-linejoin="round"/>
  <g stroke="#FFFFFF" stroke-width="8" fill="none" stroke-linecap="round" opacity=".95">
    <ellipse cx="128" cy="102" rx="30" ry="11"/>
    <path d="M98 102 v26 c0 6 13 11 30 11 s30 -5 30 -11 v-26"/>
  </g>
  <circle cx="128" cy="168" r="10" fill="url(#grn)"/>
""")


# ---------- D. Чип ИИ ----------
save("mark-d-chip.svg", """
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <g stroke="#3A4768" stroke-width="8" stroke-linecap="round">
    <path d="M78 78 v-22 M110 78 v-22 M146 78 v-22 M178 78 v-22"/>
    <path d="M78 178 v22 M110 178 v22 M146 178 v22 M178 178 v22"/>
    <path d="M78 78 h-22 M78 110 h-22 M78 146 h-22 M78 178 h-22"/>
    <path d="M178 78 h22 M178 110 h22 M178 146 h22 M178 178 h22"/>
  </g>
  <rect x="78" y="78" width="100" height="100" rx="22" fill="url(#acc)"/>
  <text x="128" y="148" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="52" font-weight="700" fill="#FFFFFF" letter-spacing="-2">AI</text>
  <circle cx="166" cy="90" r="7" fill="url(#grn)"/>
""")


def mark_group(scale, dx, dy):
    return """
  <g transform="translate(%d,%d) scale(%s)">
    <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
    <text x="34" y="170" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="104" font-weight="700"
          fill="#FFFFFF" letter-spacing="-5">1C</text>
    <g transform="translate(196,84)"><path d="%s" fill="url(#grn)"/></g>
    <path d="M40 196 H150" stroke="#7C5CFF" stroke-width="8" stroke-linecap="round"/>
  </g>
""" % (dx, dy, scale, SPARK)


# ---------- E. Горизонтальный ----------
save("logo-horizontal.svg", mark_group(0.5, 20, 30) + """
  <text x="176" y="88" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="48" font-weight="700"
        fill="#FFFFFF" letter-spacing="-1">1C-AI-Control</text>
  <text x="178" y="126" font-family="Segoe UI,Arial,Helvetica,sans-serif" font-size="21" fill="#93A4BF">
        копии · мониторинг · ИИ-проверки баз 1С</text>
  <rect x="178" y="142" width="92" height="4" rx="2" fill="url(#grn)"/>
""".replace('<rect x="8" y="8" width="720"', ''), w=720, h=180)

# ---------- F. Вертикальный ----------
save("logo-stacked.svg", mark_group(0.72, 82, 40) + """
  <text x="210" y="290" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="40" font-weight="700" fill="#FFFFFF" letter-spacing="-1">1C-AI-Control</text>
  <text x="210" y="324" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="17" fill="#93A4BF">ИИ-контроль баз 1С</text>
  <text x="210" y="358" text-anchor="middle" font-family="Segoe UI,Arial,Helvetica,sans-serif"
        font-size="14" fill="#5B6A85">v3.0.0</text>
""", w=420, h=420)

print("Готово (v2)")
