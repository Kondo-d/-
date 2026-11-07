#!/usr/bin/env python3
"""Gemini などで作った緑背景のキャラクター画像を切り抜いて、スプライト PNG にする。

    # 横一列のラインナップ → 各キャラの normal 表情
    python3 sims/import_sprites.py lineup assets/source/lineup.jpg MOCHI BISCUIT GINGER LUNA STRAY
    # 2x2 の表情シート（左上 normal / 右上 panic / 左下 cry / 右下 happy）
    python3 sims/import_sprites.py sheet assets/source/mochi.jpg MOCHI

出力: assets/sprites/<NAME>_<expr>.png（透過 PNG、顔の部分だけにトリミング）
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites"
EXPRS = ["normal", "panic", "cry", "happy"]


def key_green(img):
    """緑背景を透明にする（JPEG のノイズを考慮した柔らかいキー + 緑かぶり除去）。"""
    a = np.asarray(img.convert("RGB")).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    dom = g - np.maximum(r, b)                 # 緑の強さ
    alpha = np.clip((90 - dom) / (90 - 40), 0, 1)
    spill = alpha < 1
    g2 = np.where(spill | (dom > 0), np.minimum(g, np.maximum(r, b) + 10), g)
    rgba = np.dstack([r, g2, b, alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def runs(mask_1d, min_gap=4, min_len=10):
    """True が続く区間を返す（短い途切れはつなぐ）。"""
    idx = np.flatnonzero(mask_1d)
    if len(idx) == 0:
        return []
    out, s, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > min_gap:
            out.append((s, prev + 1)); s = i
        prev = i
    out.append((s, prev + 1))
    return [(a, b) for a, b in out if b - a >= min_len]


def crop(rgba, pad=4):
    al = np.asarray(rgba)[..., 3] > 20
    ys, xs = np.flatnonzero(al.any(1)), np.flatnonzero(al.any(0))
    if len(ys) == 0:
        return rgba
    return rgba.crop((max(0, xs[0] - pad), max(0, ys[0] - pad), xs[-1] + 1 + pad, ys[-1] + 1 + pad))


def save(img, name, expr):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}_{expr}.png"
    img.save(p)
    print(f"  {p.relative_to(OUT.parent.parent)} {img.size}")


def lineup(path, names):
    rgba = key_green(Image.open(path))
    al = np.asarray(rgba)[..., 3] > 128
    cols = runs(al.sum(0) > 2)
    if len(cols) != len(names):
        sys.exit(f"{len(names)} 体を指定しましたが、画像からは {len(cols)} 体検出されました")
    for (x0, x1), name in zip(cols, names):
        save(crop(rgba.crop((x0, 0, x1, rgba.height))), name, "normal")


def sheet(path, name):
    rgba = key_green(Image.open(path))
    w, h = rgba.size
    cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for (cx, cy), expr in zip(cells, EXPRS):
        save(crop(rgba.crop((cx * w // 2, cy * h // 2, (cx + 1) * w // 2, (cy + 1) * h // 2))), name, expr)


if __name__ == "__main__":
    mode, path, *names = sys.argv[1:]
    lineup(path, names) if mode == "lineup" else sheet(path, names[0])
