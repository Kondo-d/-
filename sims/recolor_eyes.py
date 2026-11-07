#!/usr/bin/env python3
"""スプライトの茶色い瞳を別の色に塗り替える（黒猫の目を黄色にする用）。

    python3 sims/recolor_eyes.py assets/sprites/STRAY_normal.png
"""
import colorsys
import sys

import numpy as np
from PIL import Image


def recolor(path, target_hue=50 / 360):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(float) / 255
    rgb = a[..., :3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.vectorize(lambda r, g, b: colorsys.rgb_to_hsv(r, g, b)[0])(r, g, b)
    brown = (hue > 10 / 360) & (hue < 45 / 360) & (sat > 0.3) & (mx > 0.12) & (a[..., 3] > 0.5)
    ys, xs = np.nonzero(brown)
    out = rgb.copy()
    for y, x in zip(ys, xs):
        v = min(1.0, 0.35 + mx[y, x] * 1.6)
        out[y, x] = colorsys.hsv_to_rgb(target_hue, 0.9, v)
    a[..., :3] = out
    Image.fromarray((a * 255).astype(np.uint8), "RGBA").save(path)
    print(f"{path}: {len(ys)} px を塗り替え")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        recolor(p)
