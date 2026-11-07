"""Иконка «песочница с эмблемой 1С»: 500×500, прозрачный фон, строгий стиль."""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 1000          # рисуем крупно, потом уменьшаем — так края гладкие
OUT = 500
random.seed(7)

img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# ---------- тень под песочницей ----------
shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.ellipse([(150, 760), (850, 880)], fill=(60, 40, 15, 70))
shadow = shadow.filter(ImageFilter.GaussianBlur(24))
img.alpha_composite(shadow)

# ---------- корпус песочницы ----------
WOOD_DARK = (110, 66, 32, 255)
WOOD = (150, 92, 44, 255)
WOOD_LIGHT = (182, 118, 60, 255)

# внешний короб (вид сверху с лёгким наклоном)
top = [(180, 300), (820, 300), (880, 420), (120, 420)]
front = [(120, 420), (880, 420), (860, 700), (140, 700)]
d.polygon(top, fill=WOOD_LIGHT)
d.polygon(front, fill=WOOD)

# боковые грани
d.polygon([(120, 420), (180, 300), (180, 470), (120, 560)], fill=WOOD_DARK)
d.polygon([(880, 420), (820, 300), (820, 470), (880, 560)], fill=WOOD_DARK)

# доски: линии
for y in (500, 580, 660):
    d.line([(140, y), (860, y)], fill=(126, 74, 34, 255), width=6)
for x in (300, 480, 660):
    d.line([(x, 425), (x - 8, 695)], fill=(126, 74, 34, 255), width=4)

# ---------- песок ----------
SAND = (242, 205, 108, 255)
SAND_DARK = (224, 182, 86, 255)
d.polygon([(200, 350), (800, 350), (846, 430), (154, 430)], fill=SAND_DARK)
sand = [(154, 430), (846, 430), (830, 620), (170, 620)]
d.polygon(sand, fill=SAND)

# крупинки
for _ in range(2600):
    x = random.randint(170, 830)
    y = random.randint(432, 616)
    r = random.choice([1, 1, 1, 2])
    shade = random.choice([(238, 200, 104, 255), (248, 214, 122, 255), (228, 188, 94, 255)])
    d.ellipse([(x, y), (x + r, y + r)], fill=shade)

# ---------- эмблема 1С в песке ----------
CX, CY, R = 500, 505, 150

# мягкая тень под эмблемой
em_shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
ed = ImageDraw.Draw(em_shadow)
ed.ellipse([(CX - R + 6, CY - R + 26), (CX + R + 6, CY + R + 30)], fill=(120, 84, 20, 90))
em_shadow = em_shadow.filter(ImageFilter.GaussianBlur(18))
img.alpha_composite(em_shadow)

# диск
d = ImageDraw.Draw(img)
d.ellipse([(CX - R, CY - R), (CX + R, CY + R)], fill=(250, 252, 255, 255))
d.ellipse([(CX - R, CY - R), (CX + R, CY + R)], outline=(214, 222, 232, 255), width=6)

# жёлтое кольцо 1С
R2 = R - 22
d.ellipse([(CX - R2, CY - R2), (CX + R2, CY + R2)], fill=(247, 200, 20, 255))

# красная надпись 1С
font = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 150)
text = '1С'
bbox = d.textbbox((0, 0), text, font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
d.text((CX - tw / 2 - bbox[0], CY - th / 2 - bbox[1] - 4), text, font=font, fill=(196, 22, 40, 255))

# ---------- совок и лопатка (акценты) ----------
# лопатка
d.line([(690, 350), (770, 560)], fill=(120, 200, 90, 255), width=22)
d.polygon([(752, 560), (812, 600), (770, 640), (724, 596)], fill=(132, 210, 96, 255))
d.ellipse([(676, 322), (716, 362)], fill=(104, 178, 78, 255))

# совок
d.line([(300, 360), (250, 470)], fill=(150, 200, 215, 255), width=14)
d.polygon([(214, 462), (286, 462), (268, 540), (232, 540)], fill=(120, 186, 206, 255))

# ---------- уменьшение ----------
img = img.resize((OUT, OUT), Image.LANCZOS)
img.save(r'E:\_Project\1CSmallControl\static\sandbox.png', optimize=True)
print('готово: static/sandbox.png', img.size)
