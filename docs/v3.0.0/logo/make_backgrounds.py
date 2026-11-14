#!/usr/bin/env python3
"""1C-AI-Control: варианты фонов (SVG) для светлой и тёмной темы."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BG = os.path.join(ROOT, "backgrounds")
os.makedirs(BG, exist_ok=True)

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice">'


def save(name, body, w=1920, h=1080):
    with open(os.path.join(BG, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD.format(w=w, h=h) + "\n" + body + "\n</svg>\n")
    print("  ", name)


# 1. Светлый: мягкий градиент + пятна
save("bg-1-light-soft.svg", """
  <defs>
    <linearGradient id="l1" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset="0.55" stop-color="#F4F7FD"/><stop offset="1" stop-color="#EAF0FA"/>
    </linearGradient>
    <radialGradient id="p1" cx="0.2" cy="0.1" r="0.7">
      <stop offset="0" stop-color="#7C5CFF" stop-opacity=".18"/><stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="p2" cx="0.9" cy="0.85" r="0.6">
      <stop offset="0" stop-color="#2FBF71" stop-opacity=".16"/><stop offset="1" stop-color="#2FBF71" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1920" height="1080" fill="url(#l1)"/>
  <rect width="1920" height="1080" fill="url(#p1)"/>
  <rect width="1920" height="1080" fill="url(#p2)"/>
""")


# 2. Светлый: сетка
save("bg-2-light-grid.svg", """
  <defs>
    <pattern id="g" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M48 0H0V48" fill="none" stroke="#D7E0EF" stroke-width="1"/>
    </pattern>
    <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".2"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity=".95"/>
    </linearGradient>
  </defs>
  <rect width="1920" height="1080" fill="#F7F9FD"/>
  <rect width="1920" height="1080" fill="url(#g)"/>
  <rect width="1920" height="1080" fill="url(#fade)"/>
""")


# 3. Светлый: mesh-пятна (мягкие, для лендинга)
save("bg-3-light-mesh.svg", """
  <defs>
    <filter id="blur"><feGaussianBlur stdDeviation="120"/></filter>
    <linearGradient id="base3" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EEF3FC"/>
    </linearGradient>
  </defs>
  <rect width="1920" height="1080" fill="url(#base3)"/>
  <g filter="url(#blur)" opacity=".55">
    <ellipse cx="320" cy="180" rx="420" ry="300" fill="#B9A8FF"/>
    <ellipse cx="1560" cy="240" rx="380" ry="280" fill="#A9E4C6"/>
    <ellipse cx="1180" cy="920" rx="460" ry="320" fill="#C9D6FF"/>
  </g>
""")


# 4. Тёмный: глубокий градиент + свечение
save("bg-4-dark-deep.svg", """
  <defs>
    <linearGradient id="d1" x1="0" y1="0" x2="0.7" y2="1">
      <stop offset="0" stop-color="#121A2C"/><stop offset="0.6" stop-color="#0D1320"/><stop offset="1" stop-color="#080C15"/>
    </linearGradient>
    <radialGradient id="glow1" cx="0.15" cy="0.1" r="0.65">
      <stop offset="0" stop-color="#7C5CFF" stop-opacity=".35"/><stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2" cx="0.9" cy="0.9" r="0.6">
      <stop offset="0" stop-color="#2FBF71" stop-opacity=".22"/><stop offset="1" stop-color="#2FBF71" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1920" height="1080" fill="url(#d1)"/>
  <rect width="1920" height="1080" fill="url(#glow1)"/>
  <rect width="1920" height="1080" fill="url(#glow2)"/>
""")


# 5. Тёмный: платы/схемы
save("bg-5-dark-circuit.svg", """
  <defs>
    <linearGradient id="d2" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0E1422"/><stop offset="1" stop-color="#0A0F1A"/>
    </linearGradient>
    <pattern id="circ" width="160" height="160" patternUnits="userSpaceOnUse">
      <g fill="none" stroke="#2A3550" stroke-width="1.4">
        <path d="M20 40h50v50h40"/>
        <path d="M0 120h60v-40"/>
        <path d="M120 0v40h40"/>
        <path d="M140 100h-40v60"/>
      </g>
      <g fill="#7C5CFF" opacity=".55">
        <circle cx="70" cy="90" r="3"/><circle cx="60" cy="80" r="3"/><circle cx="120" cy="40" r="3"/><circle cx="140" cy="160" r="3"/>
      </g>
    </pattern>
  </defs>
  <rect width="1920" height="1080" fill="url(#d2)"/>
  <rect width="1920" height="1080" fill="url(#circ)" opacity=".9"/>
""")


# 6. Тёмный: «сияние» (aurora-полосы)
save("bg-6-dark-aurora.svg", """
  <defs>
    <linearGradient id="d3" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1020"/><stop offset="1" stop-color="#0A0E18"/>
    </linearGradient>
    <linearGradient id="a1" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#7C5CFF" stop-opacity="0"/><stop offset=".5" stop-color="#7C5CFF" stop-opacity=".5"/><stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="a2" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2FBF71" stop-opacity="0"/><stop offset=".5" stop-color="#2FBF71" stop-opacity=".4"/><stop offset="1" stop-color="#2FBF71" stop-opacity="0"/>
    </linearGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="40"/></filter>
  </defs>
  <rect width="1920" height="1080" fill="url(#d3)"/>
  <g filter="url(#soft)">
    <path d="M-200 320 C 500 120, 1200 520, 2120 240" stroke="url(#a1)" stroke-width="160" fill="none"/>
    <path d="M-200 760 C 600 620, 1300 940, 2120 720" stroke="url(#a2)" stroke-width="120" fill="none"/>
  </g>
""")


# 7. Плитка: точки (tileable, для панели)
save("bg-7-tile-dots.svg", """
  <defs>
    <pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse">
      <circle cx="2" cy="2" r="1.6" fill="#CBD6E8"/>
    </pattern>
  </defs>
  <rect width="1920" height="1080" fill="#F8FAFE"/>
  <rect width="1920" height="1080" fill="url(#dots)"/>
""", w=1920, h=1080)


# 8. Экран входа: тёмный с водяным знаком-искрой
save("bg-8-login-hero.svg", """
  <defs>
    <linearGradient id="lh" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#141C31"/><stop offset="1" stop-color="#0A0F1A"/>
    </linearGradient>
    <radialGradient id="lglow" cx="0.75" cy="0.2" r="0.7">
      <stop offset="0" stop-color="#7C5CFF" stop-opacity=".38"/><stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="spark" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#7BE0A7"/><stop offset="1" stop-color="#2FBF71"/>
    </linearGradient>
  </defs>
  <rect width="1920" height="1080" fill="url(#lh)"/>
  <rect width="1920" height="1080" fill="url(#lglow)"/>
  <g opacity=".14" transform="translate(1480,240)">
    <path d="M0 -220 Q 50 -50 220 0 Q 50 50 0 220 Q -50 50 -220 0 Q -50 -50 0 -220 Z" fill="url(#spark)"/>
  </g>
  <g opacity=".1" stroke="#8E74FF" stroke-width="2" fill="none">
    <path d="M0 880 H520 l80 -120 120 260 90 -180 H1920"/>
  </g>
""")

print("Готово: фоны")
