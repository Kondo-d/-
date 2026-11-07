#!/usr/bin/env python3
"""チャンネルアイコン（800x800）を作る。  python3 sims/channel_art.py output/channel_icon.png"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import pets as P  # noqa: E402


def icon(path, S=800):
    img = Image.new("RGB", (S, S), (14, 14, 24))
    g = Image.new("L", (S, S), 0)
    ImageDraw.Draw(g).ellipse([60, 60, 740, 740], fill=150)
    img = Image.composite(Image.new("RGB", (S, S), (80, 35, 130)), img, g.filter(ImageFilter.GaussianBlur(90)))
    ImageDraw.Draw(img).arc([90, 90, 710, 710], -50, 230, fill=(200, 150, 255), width=22)

    def put(name, kind, expr, r, x, y, rot=0):
        sp = P.sprite(name, kind, expr, r).rotate(rot, resample=Image.BICUBIC, expand=True)
        img.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)

    put("STRAY", "black", "normal", 80, 400, 170)
    put("MOCHI", "shiba", "happy", 120, 270, 455, 8)
    put("GINGER", "tabby", "happy", 120, 530, 455, -8)
    img.save(path)


if __name__ == "__main__":
    icon(sys.argv[1] if len(sys.argv) > 1 else "output/channel_icon.png")
