#!/usr/bin/env python3
"""「Which ball escapes first?」型の縦型ショート（1080x1920）を生成する。

回転するリングの隙間から、名前付きのボール（キャラクター）が脱出を競う。
リングに当たるたびにメロディ（パブリックドメインの曲）が1音ずつ鳴る。

使い方:
    python3 sims/escape.py -o escape.mp4            # 良い展開になるシードを自動で選ぶ
    python3 sims/escape.py --seed 12 -o escape.mp4  # シードを固定
"""
import argparse
import math
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SUB = 1080, 1920, 60, 4
DT = 1.0 / (FPS * SUB)
CX, CY, R = W // 2, 1080, 430
BALL_R = 30
GRAVITY = 1400.0
GAP0, GAP_GROW = 0.22, 0.010   # リングの隙間（ラジアン）は時間とともに広がる
OMEGA = 0.9           # リングの回転速度（rad/s）
BOOST, VMAX = 1.012, 2100.0
TIME_LIMIT = 55.0
OUTRO = 3.0

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG = (14, 14, 24)

CHARACTERS = [
    ("RUBY", (255, 70, 90)),
    ("SKY", (60, 170, 255)),
    ("LIME", (90, 230, 110)),
    ("SUNNY", (255, 205, 50)),
]

# エリーゼのために（ベートーヴェン、パブリックドメイン）冒頭の MIDI ノート番号
MELODY = [76, 75, 76, 75, 76, 71, 74, 72, 69, 60, 64, 69, 71, 64, 68, 71, 72,
          64, 76, 75, 76, 75, 76, 71, 74, 72, 69, 60, 64, 69, 71, 64, 72, 71, 69]


def gap_width(t):
    return GAP0 + GAP_GROW * t


class Ball:
    def __init__(self, name, color, x, y, vx, vy):
        self.name, self.color = name, color
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.free = False      # 隙間を通過中・脱出後はリングと衝突しない
        self.escaped_at = None
        self.trail = []


def simulate(seed):
    """物理シミュレーションを回し、フレームごとの状態とイベントを返す。"""
    rng = random.Random(seed)
    balls = []
    for i, (name, color) in enumerate(CHARACTERS):
        a = math.pi / 2 + (i - 1.5) * 0.5
        ang = rng.uniform(0, 2 * math.pi)
        sp = rng.uniform(500, 800)
        balls.append(Ball(name, color, CX + 150 * math.cos(a), CY - 120 + 60 * math.sin(a),
                          sp * math.cos(ang), sp * math.sin(ang)))
    frames, bounces, escapes = [], [], []
    t, step = 0.0, 0
    end_t = None
    while True:
        gap_ang = (OMEGA * t) % (2 * math.pi)
        GAP = gap_width(t)
        for b in balls:
            b.vy += GRAVITY * DT
            b.x += b.vx * DT
            b.y += b.vy * DT
            dx, dy = b.x - CX, b.y - CY
            d = math.hypot(dx, dy) or 1e-6
            if b.escaped_at is None and not b.free and d + BALL_R >= R:
                ang = math.atan2(dy, dx)
                diff = (ang - gap_ang + math.pi) % (2 * math.pi) - math.pi
                if abs(diff) < GAP / 2 - BALL_R / R:
                    b.free = True
                else:
                    nx, ny = dx / d, dy / d
                    vn = b.vx * nx + b.vy * ny
                    if vn > 0:
                        b.vx -= 2 * vn * nx
                        b.vy -= 2 * vn * ny
                        sp = math.hypot(b.vx, b.vy)
                        k = min(BOOST, VMAX / sp) if sp > 0 else 1
                        b.vx *= k
                        b.vy *= k
                        bounces.append((t, vn))
                    b.x = CX + nx * (R - BALL_R)
                    b.y = CY + ny * (R - BALL_R)
            if b.free and b.escaped_at is None and d - BALL_R > R + 2:
                b.escaped_at = t
                escapes.append((t, b.name))
            if b.free and b.escaped_at is None and d + BALL_R < R - 4:
                b.free = False  # 隙間から戻ってきた
        # ボール同士の衝突（リング内のみ）
        inside = [b for b in balls if b.escaped_at is None]
        for i in range(len(inside)):
            for j in range(i + 1, len(inside)):
                a, c = inside[i], inside[j]
                dx, dy = c.x - a.x, c.y - a.y
                d = math.hypot(dx, dy)
                if 0 < d < 2 * BALL_R:
                    nx, ny = dx / d, dy / d
                    rel = (a.vx - c.vx) * nx + (a.vy - c.vy) * ny
                    if rel > 0:
                        a.vx -= rel * nx; a.vy -= rel * ny
                        c.vx += rel * nx; c.vy += rel * ny
                    ov = (2 * BALL_R - d) / 2
                    a.x -= nx * ov; a.y -= ny * ov
                    c.x += nx * ov; c.y += ny * ov
        t += DT
        step += 1
        if step % SUB == 0:
            frames.append((gap_ang, GAP, [(b.x, b.y, b.escaped_at is not None) for b in balls]))
        if end_t is None and (all(b.escaped_at is not None for b in balls) or t >= TIME_LIMIT):
            end_t = t
        if end_t is not None and t >= end_t + OUTRO:
            break
    return frames, bounces, escapes, end_t


def score(escapes, end_t):
    """展開の良さ: 最初の脱出が早すぎず遅すぎず、全員が時間内に、間隔が空いているほど良い。"""
    if len(escapes) < len(CHARACTERS):
        return -1
    ts = [e[0] for e in escapes]
    if not (7 <= ts[0] <= 20) or ts[-1] > 48:
        return -1
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    return min(gaps)


def pick_seed(max_tries=300):
    best = (-1, None)
    for seed in range(max_tries):
        _, _, esc, end_t = simulate(seed)
        s = score(esc, end_t)
        if s > best[0]:
            best = (s, seed)
            print(f"  seed {seed}: 脱出 {[round(e[0], 1) for e in esc]} 最小間隔 {s:.1f}s", file=sys.stderr)
        if s >= 4:
            break
    if best[1] is None:
        sys.exit("条件を満たすシードが見つかりませんでした")
    return best[1]


# ---------- 音 ----------
RATE = 44100


def tone(freq, dur, vol):
    t = np.arange(int(dur * RATE)) / RATE
    env = np.minimum(1, t / 0.004) * np.exp(-t * 6)
    w = np.sin(2 * np.pi * freq * t) + 0.45 * np.sin(4 * np.pi * freq * t) + 0.2 * np.sin(6 * np.pi * freq * t)
    return w * env * vol


def build_audio(path, bounces, escapes, end_t, total):
    out = np.zeros(int((total + 1) * RATE))

    def add(sig, at):
        i = int(at * RATE)
        n = min(len(sig), len(out) - i)
        if n > 0:
            out[i:i + n] += sig[:n]

    note, last = 0, -1.0
    for t, vn in bounces:
        if t - last < 0.06:   # 同時に鳴りすぎないように間引く
            continue
        last = t
        f = 440 * 2 ** ((MELODY[note % len(MELODY)] - 69) / 12)
        add(tone(f, 0.9, 0.35 + 0.4 * min(1, vn / 1500)), t)
        note += 1
    for t, _ in escapes:
        for k, m in enumerate([72, 76, 79, 84]):
            add(tone(440 * 2 ** ((m - 69) / 12), 1.2, 0.35), t + k * 0.07)
    for m in [57, 64, 69, 72, 76]:
        add(tone(440 * 2 ** ((m - 69) / 12), 2.5, 0.3), end_t + 0.2)
    # 簡易リバーブ
    rev = out.copy()
    for delay, g in [(0.045, 0.35), (0.11, 0.22), (0.19, 0.12)]:
        k = int(delay * RATE)
        rev[k:] += out[:-k] * g
    rev = rev / (np.abs(rev).max() or 1) * 0.85
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(RATE)
        wf.writeframes((rev * 32767).astype(np.int16).tobytes())


# ---------- 描画 ----------
def mix(c, k):
    return tuple(int(BG[i] + (c[i] - BG[i]) * k) for i in range(3))


def centered(d, y, text, font, fill):
    b = d.textbbox((0, 0), text, font=font)
    d.text(((W - (b[2] - b[0])) // 2 - b[0], y), text, font=font, fill=fill)


def render(frames, escapes, end_t, out_path, audio_path):
    f_title = ImageFont.truetype(FONT, 78)
    f_sub = ImageFont.truetype(FONT, 46)
    f_board = ImageFont.truetype(FONT, 44)
    f_name = ImageFont.truetype(FONT, 26)
    f_win = ImageFont.truetype(FONT, 110)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    trails = [[] for _ in CHARACTERS]
    flash = {}
    for fi, (gap_ang, GAP, states) in enumerate(frames):
        t = fi / FPS
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        # ヘッダー
        centered(d, 150, "WHICH BALL", f_title, (255, 255, 255))
        centered(d, 240, "ESCAPES FIRST?", f_title, (255, 215, 80))
        # 順位表
        done = [e for e in escapes if e[0] <= t]
        for k, (name, color) in enumerate(CHARACTERS):
            x = 90 + k * 235
            rank = next((i + 1 for i, e in enumerate(done) if e[1] == name), None)
            d.ellipse([x, 395, x + 40, 435], fill=color)
            label = f"{name}" + (f" #{rank}" if rank else "")
            d.text((x + 52, 393), label, font=f_name if not rank else f_name,
                   fill=(255, 255, 255) if rank else (150, 150, 165))
        # リング（隙間以外を弧で描く）
        start = math.degrees(gap_ang + GAP / 2)
        end = math.degrees(gap_ang - GAP / 2 + 2 * math.pi)
        hue = (t * 0.05) % 1
        ring_col = tuple(int(160 + 95 * math.sin(2 * math.pi * (hue + o))) for o in (0, 1 / 3, 2 / 3))
        for wdt, k in [(26, 0.18), (14, 0.45), (8, 1.0)]:
            d.arc([CX - R - wdt // 2, CY - R - wdt // 2, CX + R + wdt // 2, CY + R + wdt // 2],
                  start, end, fill=mix(ring_col, k), width=wdt)
        # ボールと軌跡
        for i, ((x, y, esc), (name, color)) in enumerate(zip(states, CHARACTERS)):
            tr = trails[i]
            tr.append((x, y))
            del tr[:-14]
            for j, (px, py) in enumerate(tr[:-1]):
                k = (j + 1) / len(tr) * 0.5
                r = BALL_R * (0.4 + 0.6 * (j + 1) / len(tr))
                d.ellipse([px - r, py - r, px + r, py + r], fill=mix(color, k))
            d.ellipse([x - BALL_R - 8, y - BALL_R - 8, x + BALL_R + 8, y + BALL_R + 8], fill=mix(color, 0.3))
            d.ellipse([x - BALL_R, y - BALL_R, x + BALL_R, y + BALL_R], fill=color)
            b = d.textbbox((0, 0), name, font=f_name)
            d.text((x - (b[2] - b[0]) / 2, y - BALL_R - 38), name, font=f_name, fill=(235, 235, 245))
        # 脱出の瞬間テロップ
        for k, (et, name) in enumerate(escapes):
            if 0 <= t - et < 1.4:
                color = dict(CHARACTERS)[name]
                ordinal = ["1ST", "2ND", "3RD", "4TH"][k]
                centered(d, 1600, f"{name} ESCAPED! {ordinal}", f_sub, color)
        # 下部の呼びかけ
        if t < end_t:
            centered(d, 1700, "Comment your pick!", f_sub, (170, 170, 190))
        # エンディング
        if t >= end_t + 0.2 and escapes:
            name = escapes[0][1]
            color = dict(CHARACTERS)[name]
            ov = Image.new("RGB", (W, H), (0, 0, 0))
            img = Image.blend(img, ov, min(0.75, (t - end_t) * 1.5))
            d = ImageDraw.Draw(img)
            centered(d, 760, "WINNER", f_sub, (255, 255, 255))
            centered(d, 830, name, f_win, color)
            centered(d, 1000, "Did you guess right?", f_sub, (220, 220, 230))
            centered(d, 1080, "Follow for the next race!", f_sub, (255, 215, 80))
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg でエラーが発生しました")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default="escape.mp4")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else pick_seed()
    frames, bounces, escapes, end_t = simulate(seed)
    total = len(frames) / FPS
    print(f"seed={seed} 長さ={total:.1f}s 脱出={[(round(t, 1), n) for t, n in escapes]}")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        build_audio(wav, bounces, escapes, end_t, total)
        render(frames, escapes, end_t, args.output, wav)
    print(f"作成しました: {args.output}")


if __name__ == "__main__":
    main()
