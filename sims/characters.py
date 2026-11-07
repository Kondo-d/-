"""犬猫キャラクターのスプライトをコードで描く（完全オリジナル）。

draw(kind, expr, r) -> 半径 r の顔を中心に持つ RGBA 画像（耳の分だけ余白あり）
  kind: shiba / beagle / tabby / gray / black
  expr: normal / panic / cry / happy
4倍で描いてから縮小してアンチエイリアスをかける。
"""
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

SS = 4  # スーパーサンプリング倍率

# 種類ごとの配色
SPECIES = {
    "shiba":  dict(body=(232, 150, 80), mark=(255, 246, 232), ear_in=(255, 214, 180), dog=True),
    "beagle": dict(body=(205, 140, 82), mark=(255, 250, 240), ear=(110, 62, 34), dog=True),
    "tabby":  dict(body=(246, 160, 70), mark=(206, 106, 36), ear_in=(255, 186, 186), dog=False),
    "gray":   dict(body=(150, 160, 182), mark=(245, 245, 250), ear_in=(255, 190, 200), dog=False),
    "black":  dict(body=(40, 40, 50), mark=(40, 40, 50), ear_in=(110, 70, 90), dog=False),
}
INK = (34, 24, 28)
TEAR = (120, 200, 255)


def _ell(d, cx, cy, rx, ry, **kw):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], **kw)


@lru_cache(maxsize=None)
def draw(kind, expr, r):
    sp = SPECIES[kind]
    R = r * SS
    size = int(R * 2 * 1.5)
    cx, cy = size / 2, size / 2 + R * 0.12
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    outline = (215, 215, 230) if kind == "black" else INK
    ow = max(2, int(R * 0.07))

    # --- 耳（頭の後ろ） ---
    if kind == "shiba" or not sp["dog"]:
        tall = 0.95 if kind == "shiba" else 1.05
        for s in (-1, 1):
            base_out = (cx + s * R * 0.92, cy - R * 0.25)
            base_in = (cx + s * R * 0.22, cy - R * 0.85)
            tip = (cx + s * R * 0.78, cy - R * (0.55 + tall))
            d.polygon([base_out, tip, base_in], fill=sp["body"], outline=outline, width=ow)
            inner = [(cx + s * R * 0.78, cy - R * 0.45), (cx + s * R * 0.74, cy - R * (0.45 + tall * 0.8)),
                     (cx + s * R * 0.38, cy - R * 0.8)]
            d.polygon(inner, fill=sp["ear_in"])

    # --- 頭と模様（頭の形でマスク） ---
    mask = Image.new("L", (size, size), 0)
    _ell(ImageDraw.Draw(mask), cx, cy, R, R, fill=255)
    face = Image.new("RGBA", (size, size), sp["body"] + (255,))
    fd = ImageDraw.Draw(face)
    if kind == "shiba":
        _ell(fd, cx - R * 0.42, cy + R * 0.42, R * 0.62, R * 0.5, fill=sp["mark"])
        _ell(fd, cx + R * 0.42, cy + R * 0.42, R * 0.62, R * 0.5, fill=sp["mark"])
        _ell(fd, cx - R * 0.36, cy - R * 0.36, R * 0.13, R * 0.08, fill=sp["mark"])  # 麻呂眉
        _ell(fd, cx + R * 0.36, cy - R * 0.36, R * 0.13, R * 0.08, fill=sp["mark"])
    elif kind == "beagle":
        fd.rectangle([cx - R * 0.12, cy - R * 1.1, cx + R * 0.12, cy], fill=sp["mark"])
        _ell(fd, cx, cy + R * 0.42, R * 0.5, R * 0.42, fill=sp["mark"])
    elif kind == "tabby":
        for dx, h in ((-0.3, 0.42), (0, 0.5), (0.3, 0.42)):
            fd.rounded_rectangle([cx + R * (dx - 0.07), cy - R * 1.05, cx + R * (dx + 0.07), cy - R * (1.05 - h)],
                                 radius=R * 0.07, fill=sp["mark"])
        for s in (-1, 1):
            for k in (0, 1):
                y = cy + R * (0.05 + k * 0.2)
                xa, xb = sorted((cx + s * R * 0.78, cx + s * R * 1.05))
                fd.rounded_rectangle([xa, y, xb, y + R * 0.1],
                                     radius=R * 0.05, fill=sp["mark"])
    elif kind == "gray":
        _ell(fd, cx, cy + R * 0.48, R * 0.55, R * 0.42, fill=sp["mark"])
    face.putalpha(mask)
    img.alpha_composite(face)
    _ell(d, cx, cy, R, R, outline=outline, width=ow)

    # --- 垂れ耳（頭の前） ---
    if kind == "beagle":
        for s in (-1, 1):
            ear = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            _ell(ImageDraw.Draw(ear), cx + s * R * 0.88, cy + R * 0.05, R * 0.3, R * 0.62,
                 fill=sp["ear"], outline=outline, width=ow)
            ear = ear.rotate(-s * 12, center=(cx + s * R * 0.88, cy - R * 0.5), resample=Image.BICUBIC)
            img.alpha_composite(ear)

    # --- 表情 ---
    ex, ey = R * 0.36, cy - R * 0.02
    if kind == "black":
        eye_col = (250, 220, 70)
    else:
        eye_col = INK
    blush = expr == "happy" or (expr == "normal" and kind in ("shiba", "tabby"))
    if blush:
        for s in (-1, 1):
            b = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            _ell(ImageDraw.Draw(b), cx + s * R * 0.58, cy + R * 0.25, R * 0.17, R * 0.1, fill=(255, 120, 140, 130))
            img.alpha_composite(b)
    for s in (-1, 1):
        x = cx + s * ex
        if expr == "normal":
            if kind == "black":
                _ell(d, x, ey, R * 0.16, R * 0.19, fill=eye_col)
                _ell(d, x, ey, R * 0.04, R * 0.15, fill=INK)
            else:
                _ell(d, x, ey, R * 0.12, R * 0.15, fill=eye_col)
                _ell(d, x + R * 0.04, ey - R * 0.05, R * 0.045, R * 0.045, fill=(255, 255, 255))
        elif expr == "panic":
            _ell(d, x, ey - R * 0.04, R * 0.2, R * 0.23, fill=(255, 255, 255), outline=INK, width=ow // 2)
            _ell(d, x, ey - R * 0.02, R * 0.07, R * 0.07, fill=INK)
        elif expr == "cry":
            d.arc([x - R * 0.17, ey - R * 0.12, x + R * 0.17, ey + R * 0.16], 200, 340, fill=eye_col, width=ow)
            d.rounded_rectangle([x - R * 0.07, ey + R * 0.02, x + R * 0.07, cy + R * 0.85],
                                radius=R * 0.07, fill=TEAR)
        elif expr == "happy":
            d.arc([x - R * 0.17, ey - R * 0.05, x + R * 0.17, ey + R * 0.25], 200, 340, fill=eye_col, width=ow)

    # 鼻
    ny = cy + R * 0.2
    if sp["dog"]:
        _ell(d, cx, ny, R * 0.13, R * 0.09, fill=INK)
    else:
        d.polygon([(cx - R * 0.08, ny - R * 0.05), (cx + R * 0.08, ny - R * 0.05), (cx, ny + R * 0.04)],
                  fill=(255, 140, 160))
    # 口
    mw = ow * 0.8
    if expr == "normal":
        for x0 in (cx - R * 0.22, cx):
            d.arc([x0, ny - R * 0.02, x0 + R * 0.22, ny + R * 0.2], 0, 180, fill=INK, width=int(mw))
    elif expr == "panic":
        _ell(d, cx, ny + R * 0.27, R * 0.1, R * 0.13, fill=(90, 20, 30), outline=INK, width=int(mw))
    elif expr == "cry":
        _ell(d, cx, ny + R * 0.28, R * 0.2, R * 0.12, fill=(90, 20, 30), outline=INK, width=int(mw))
    elif expr == "happy":
        d.chord([cx - R * 0.2, ny + R * 0.02, cx + R * 0.2, ny + R * 0.42], 0, 180, fill=(110, 25, 40), outline=INK,
                width=int(mw))
        _ell(d, cx, ny + R * 0.32, R * 0.1, R * 0.07, fill=(255, 120, 140))
    # ひげ（猫）
    if not sp["dog"]:
        wc = (230, 230, 240) if kind == "black" else (60, 50, 55)
        for s in (-1, 1):
            for k in (-1, 0, 1):
                d.line([cx + s * R * 0.42, ny + R * 0.08 + k * R * 0.08,
                        cx + s * R * 0.95, ny + k * R * 0.16], fill=wc, width=max(1, ow // 2))
    # 汗（焦り）
    if expr == "panic":
        sx, sy = cx + R * 0.82, cy - R * 0.62
        d.polygon([(sx, sy - R * 0.22), (sx - R * 0.1, sy), (sx + R * 0.1, sy)], fill=TEAR)
        _ell(d, sx, sy + R * 0.02, R * 0.1, R * 0.1, fill=TEAR)

    return img.resize((size // SS, size // SS), Image.LANCZOS)


def sheet(path, names):
    """キャラクター確認用シート（行=キャラ、列=表情）。"""
    from PIL import ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    exprs = ["normal", "panic", "cry", "happy"]
    r, cell = 80, 280
    W, H = 260 + cell * len(exprs), 90 + cell * len(names)
    out = Image.new("RGB", (W, H), (14, 14, 24))
    d = ImageDraw.Draw(out)
    for j, e in enumerate(exprs):
        d.text((260 + j * cell + 60, 30), e.upper(), font=font, fill=(200, 200, 215))
    for i, (name, kind, team) in enumerate(names):
        y = 90 + i * cell
        d.text((30, y + cell // 2 - 40), name, font=font, fill=(255, 255, 255))
        d.text((30, y + cell // 2), team, font=font, fill=(150, 150, 170))
        for j, e in enumerate(exprs):
            sp = draw(kind, e, r)
            out.paste(sp, (260 + j * cell + (cell - sp.width) // 2, y + (cell - sp.height) // 2), sp)
    out.save(path)


if __name__ == "__main__":
    import sys
    sheet(sys.argv[1] if len(sys.argv) > 1 else "characters.png", [
        ("MOCHI", "shiba", "DOGS"), ("BISCUIT", "beagle", "DOGS"),
        ("GINGER", "tabby", "CATS"), ("LUNA", "gray", "CATS"), ("???", "black", "STRAY"),
    ])
