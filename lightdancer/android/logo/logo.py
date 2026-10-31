import math, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

S = 1024

def beam(size, origin, angle, length, spread, color, alpha=170):
    """светлый конус из точки origin под углом angle (градусы от вертикали вниз)"""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    ox, oy = origin
    a = math.radians(angle)
    w = math.radians(spread)
    p1 = (ox + length * math.sin(a - w), oy + length * math.cos(a - w))
    p2 = (ox + length * math.sin(a + w), oy + length * math.cos(a + w))
    d.polygon([origin, p1, p2], fill=alpha)
    # затухание по длине
    grad = Image.new("L", (size, size), 0)
    gd = ImageDraw.Draw(grad)
    for r in range(int(length), 0, -8):
        v = int(255 * (1 - r / length) ** 0.35)
        gd.ellipse([ox - r, oy - r, ox + r, oy + r], fill=v)
    mask = ImageChops.multiply(mask, grad).filter(ImageFilter.GaussianBlur(size / 120))
    layer.paste(Image.new("RGBA", (size, size), color + (255,)), (0, 0), mask)
    return layer

def icon(size=S):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # фон: тёмный скруглённый квадрат с лёгким градиентом
    bg = Image.new("RGBA", (size, size))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / size
        bd.line([(0, y), (size, y)], fill=(int(18 + 20 * t), int(14 + 6 * t), int(40 + 30 * t), 255))
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    img.paste(bg, (0, 0), m)

    f = size / 1024
    heads = [(250 * f, 150 * f, 22, (255, 40, 160)),     # маджента
             (512 * f, 120 * f, -4, (60, 200, 255)),     # циан
             (774 * f, 150 * f, -24, (255, 180, 40))]    # янтарь
    for x, y, ang, col in heads:
        b = beam(size, (x, y), ang, 780 * f, 10, col, 255)
        img = Image.alpha_composite(img, b)
        img = Image.alpha_composite(img, b)
    # приборы
    d = ImageDraw.Draw(img)
    for x, y, ang, col in heads:
        r = 46 * f
        d.ellipse([x - r, y - r, x + r, y + r], fill=(30, 30, 44, 255), outline=(220, 220, 235, 255), width=int(8 * f))
        r2 = 22 * f
        d.ellipse([x - r2, y - r2, x + r2, y + r2], fill=col + (255,))
    # звуковая волна внизу: «танцующие» столбики
    bars = [0.35, 0.6, 0.9, 0.55, 1.0, 0.7, 0.45, 0.8, 0.5, 0.3]
    n = len(bars)
    left, right, base = 170 * f, 854 * f, 860 * f
    w = (right - left) / n
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, v in enumerate(bars):
        x0 = left + i * w + w * 0.18
        x1 = left + (i + 1) * w - w * 0.18
        h = v * 230 * f
        t = i / (n - 1)
        col = (int(255 * (1 - t) + 60 * t), int(40 * (1 - t) + 200 * t), int(160 * (1 - t) + 255 * t), 255)
        gd.rounded_rectangle([x0, base - h, x1, base], radius=int(w * 0.25), fill=col)
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(14 * f)))
    img = Image.alpha_composite(img, glow)
    # обрезать по скруглённому квадрату
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), m)
    return out

ic = icon()
ic.save("lightdancer_icon_1024.png")
for name, px in [("xxxhdpi", 192), ("xxhdpi", 144), ("xhdpi", 96), ("hdpi", 72), ("mdpi", 48)]:
    ic.resize((px, px), Image.LANCZOS).save(f"ic_{name}.png")
ic.resize((512, 512), Image.LANCZOS).save("lightdancer_icon_512.png")

# горизонтальный логотип с надписью
W, H = 2000, 560
logo = Image.new("RGBA", (W, H), (14, 12, 26, 255))
logo.paste(ic.resize((440, 440), Image.LANCZOS), (60, 60), ic.resize((440, 440), Image.LANCZOS))
d = ImageDraw.Draw(logo)
fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 190)
fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 56)
x = 560
fp = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 50)
d.text((x + 8, 70), 'Ian Konsta presents', font=fp, fill=(200, 200, 220))
d.text((x, 150), "Light", font=fb, fill=(245, 245, 250))
lw = d.textlength("Light", font=fb)
# «Dancer» градиентом маджента → циан
txt = Image.new("L", (W, H), 0)
ImageDraw.Draw(txt).text((x + lw, 150), "Dancer", font=fb, fill=255)
grad = Image.new("RGBA", (W, H))
gd = ImageDraw.Draw(grad)
for i in range(W):
    t = max(0, min(1, (i - x - lw) / 640))
    gd.line([(i, 0), (i, H)], fill=(int(255 * (1 - t) + 60 * t), int(40 * (1 - t) + 200 * t), int(160 * (1 - t) + 255 * t), 255))
logo.paste(grad, (0, 0), txt)
d.text((x + 8, 380), "музыка → свет  ·  grandMA2", font=fs, fill=(160, 160, 185))
logo.save("lightdancer_logo.png")
print("ok")
