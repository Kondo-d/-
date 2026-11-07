#!/usr/bin/env python3
"""シーン定義(JSON)からテロップ付きの MP4 動画を生成するスクリプト。

使い方:
    python3 make_video.py examples/sample.json -o output.mp4

必要なもの: Python 3, Pillow, numpy, ffmpeg (libx264 / aac)
"""
import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONTS = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
]


def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def find_font(path):
    for p in ([path] if path else []) + DEFAULT_FONTS:
        if p and Path(p).exists():
            return p
    sys.exit("日本語フォントが見つかりません。JSON の \"font\" でパスを指定してください。")


def gradient(w, h, c1, c2):
    """左上→右下の斜めグラデーション背景。"""
    y, x = np.mgrid[0:h, 0:w]
    t = ((x / w) + (y / h)) / 2.0
    a, b = np.array(hex_rgb(c1), float), np.array(hex_rgb(c2), float)
    return (a + (b - a) * t[..., None]).astype(np.uint8)


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def text_layer(w, h, scene, font_path):
    """テキストを透明レイヤーに描画して (RGBA配列) を返す。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = hex_rgb(scene.get("color", "#FFFFFF"))
    lines = []
    if scene.get("title"):
        lines.append((scene["title"], ImageFont.truetype(font_path, int(h * 0.09))))
    if scene.get("subtitle"):
        lines.append((scene["subtitle"], ImageFont.truetype(font_path, int(h * 0.045))))
    gap = int(h * 0.04)
    sizes = [d.textbbox((0, 0), t, font=f) for t, f in lines]
    total = sum(b[3] - b[1] for b in sizes) + gap * (len(lines) - 1)
    y = (h - total) // 2
    for (t, f), b in zip(lines, sizes):
        tw, th = b[2] - b[0], b[3] - b[1]
        x = (w - tw) // 2 - b[0]
        d.text((x + 3, y - b[1] + 3), t, font=f, fill=(0, 0, 0, 90))  # 影
        d.text((x, y - b[1]), t, font=f, fill=color + (255,))
        y += th + gap
    return np.asarray(img).astype(np.float32)


def render_frames(cfg, font_path):
    w, h, fps = cfg["width"], cfg["height"], cfg["fps"]
    scenes = cfg["scenes"]
    total_frames = sum(int(s["duration"] * fps) for s in scenes)
    fade = cfg.get("fade", 0.6)
    done = 0
    for s in scenes:
        bg = gradient(w, h, *s.get("bg", ["#1e3c72", "#2a5298"])).astype(np.float32)
        layer = text_layer(w, h, s, font_path)
        rgb, alpha = layer[..., :3], layer[..., 3:] / 255.0
        n = int(s["duration"] * fps)
        slide = int(h * 0.03)
        for i in range(n):
            t = i / fps
            remain = s["duration"] - t
            # テキスト: フェードイン + 下から少しスライド
            k = ease(t / 0.8)
            a = alpha * k
            shifted_rgb = np.roll(rgb, int(slide * (1 - k)), axis=0)
            shifted_a = np.roll(a, int(slide * (1 - k)), axis=0)
            frame = bg * (1 - shifted_a) + shifted_rgb * shifted_a
            # シーン切替: 黒フェード
            br = min(1.0, t / fade, remain / fade)
            frame *= br
            # 進捗バー
            p = int(w * (done + i + 1) / total_frames)
            frame[h - 6:h, :p] = frame[h - 6:h, :p] * 0.3 + 255 * 0.7
            yield frame.astype(np.uint8).tobytes()
        done += n


def make_bgm(path, seconds, rate=44100):
    """簡単なアンビエント風BGM(和音のパッド)を合成して WAV 保存。"""
    t = np.arange(int(seconds * rate)) / rate
    chords = [[261.6, 329.6, 392.0], [220.0, 261.6, 329.6],
              [174.6, 220.0, 261.6], [196.0, 246.9, 293.7]]
    out = np.zeros_like(t)
    seg = 4.0
    for idx in range(int(np.ceil(seconds / seg))):
        m = (t >= idx * seg) & (t < (idx + 1) * seg + 0.5)
        lt = t[m] - idx * seg
        env = np.minimum(1, lt / 0.8) * np.clip((seg + 0.5 - lt) / 1.0, 0, 1)
        for f in chords[idx % len(chords)]:
            out[m] += np.sin(2 * np.pi * f * lt) * env + 0.3 * np.sin(4 * np.pi * f * lt) * env
    out *= np.minimum(1, t / 1.5) * np.minimum(1, (seconds - t) / 1.5)
    out = out / (np.abs(out).max() or 1) * 0.25
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes((out * 32767).astype(np.int16).tobytes())


def main():
    ap = argparse.ArgumentParser(description="シーンJSONから動画を作成")
    ap.add_argument("config", help="シーン定義の JSON ファイル")
    ap.add_argument("-o", "--output", default="output.mp4")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cfg.setdefault("width", 1280)
    cfg.setdefault("height", 720)
    cfg.setdefault("fps", 30)
    font_path = find_font(cfg.get("font"))
    duration = sum(s["duration"] for s in cfg["scenes"])

    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{cfg['width']}x{cfg['height']}", "-r", str(cfg["fps"]), "-i", "-"]
        audio = cfg.get("audio")
        if audio == "bgm":
            audio = Path(tmp) / "bgm.wav"
            make_bgm(audio, duration)
        if audio:
            cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "160k", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                "-movflags", "+faststart", args.output]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for frame in render_frames(cfg, font_path):
            proc.stdin.write(frame)
        proc.stdin.close()
        if proc.wait() != 0:
            sys.exit("ffmpeg でエラーが発生しました")
    print(f"作成しました: {args.output} ({duration:.1f}秒)")


if __name__ == "__main__":
    main()
