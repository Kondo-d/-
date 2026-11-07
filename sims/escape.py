#!/usr/bin/env python3
"""「Which ball escapes first?」型の縦型ショート（1080x1920）を生成する。

回転するリングの隙間から、名前付きのボール（キャラクター）が脱出を競う。
リングに当たるたびにメロディ（パブリックドメインの曲）が1音ずつ鳴る。

意外性の仕掛け:
  - TWIST イベント: レース中に突然ルールが変わる（重力反転・逆回転・高速回転・謎のボール乱入）
  - ニアミス: 隙間ギリギリで弾かれた瞬間をスローにして「SO CLOSE!」
  - 脱出の瞬間（最初と最後）はスローモーション + 画面シェイク
  - シード選びで「どんでん返し」（乱入した謎のボールが勝つ等）のある展開を優先

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
OMEGA = 0.9                    # リングの回転速度（rad/s）
BOOST, VMAX = 1.012, 2100.0
TIME_LIMIT = 55.0
OUTRO = 3.0
SLOW = 0.3                     # スローモーションの速さ

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG = (14, 14, 24)

CHARACTERS = [
    ("RUBY", (255, 70, 90)),
    ("SKY", (60, 170, 255)),
    ("LIME", (90, 230, 110)),
    ("SUNNY", (255, 205, 50)),
]
MYSTERY = ("???", (40, 40, 48))   # 途中で乱入する謎のボール

TWISTS = {
    "REVERSE": "RING REVERSES!",
    "FLIP": "GRAVITY FLIP!",
    "TURBO": "TURBO SPIN!",
    "MYSTERY": "MYSTERY BALL JOINS!",
}

# エリーゼのために（ベートーヴェン、パブリックドメイン）冒頭の MIDI ノート番号
MELODY = [76, 75, 76, 75, 76, 71, 74, 72, 69, 60, 64, 69, 71, 64, 68, 71, 72,
          64, 76, 75, 76, 75, 76, 71, 74, 72, 69, 60, 64, 69, 71, 64, 72, 71, 69]


class Ball:
    def __init__(self, name, color, x, y, vx, vy, born=0.0):
        self.name, self.color = name, color
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.born = born
        self.free = False      # 隙間を通過中・脱出後はリングと衝突しない
        self.escaped_at = None
        self.last_near = -9.0


def gap_width(t):
    return GAP0 + GAP_GROW * t


def plan_twists(rng):
    """TWIST の発生時刻と種類を決める。謎のボールは必ず1回登場。"""
    kinds = ["MYSTERY"] + rng.sample(["REVERSE", "FLIP", "TURBO"], 2)
    rng.shuffle(kinds)
    times = [rng.uniform(5.5, 8.0), rng.uniform(12.5, 15.0), rng.uniform(19.5, 22.0)]
    return list(zip(times, kinds))


class Sim:
    """物理シミュレーション。全サブステップの状態を記録する。"""

    def __init__(self, seed):
        rng = random.Random(seed)
        self.rng = rng
        self.balls = []
        for i, (name, color) in enumerate(CHARACTERS):
            a = math.pi / 2 + (i - 1.5) * 0.5
            ang = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(500, 800)
            self.balls.append(Ball(name, color, CX + 150 * math.cos(a), CY - 120 + 60 * math.sin(a),
                                   sp * math.cos(ang), sp * math.sin(ang)))
        self.twists = plan_twists(rng)
        self.states = []       # 各サブステップ: (t, ring_angle, gap, [(x, y, alive_in_view)...])
        self.bounces, self.escapes, self.near = [], [], []
        self.end_t = None

    def run(self):
        t, ring, omega, grav = 0.0, 0.0, OMEGA, GRAVITY
        flip_until = -1
        pending = list(self.twists)
        while True:
            # TWIST の発動
            while pending and t >= pending[0][0]:
                _, kind = pending.pop(0)
                if kind == "REVERSE":
                    omega = -omega
                elif kind == "TURBO":
                    omega *= 2.2
                elif kind == "FLIP":
                    grav, flip_until = -GRAVITY, t + 4.0
                elif kind == "MYSTERY":
                    ang = self.rng.uniform(0, 2 * math.pi)
                    self.balls.append(Ball(*MYSTERY, CX, CY, 900 * math.cos(ang), 900 * math.sin(ang), born=t))
            if flip_until > 0 and t >= flip_until:
                grav, flip_until = GRAVITY, -1
            gap = gap_width(t)
            for b in self.balls:
                self._move(b, t, ring, gap, grav)
            self._collide()
            ring = (ring + omega * DT) % (2 * math.pi)
            self.states.append((t, ring, gap, [(b.x, b.y) for b in self.balls]))
            t += DT
            if self.end_t is None and (all(b.escaped_at is not None for b in self.balls) or t >= TIME_LIMIT):
                self.end_t = t
            if self.end_t is not None and t >= self.end_t + OUTRO:
                return self

    def _move(self, b, t, ring, gap, grav):
        b.vy += grav * DT
        b.x += b.vx * DT
        b.y += b.vy * DT
        dx, dy = b.x - CX, b.y - CY
        d = math.hypot(dx, dy) or 1e-6
        if b.escaped_at is None and not b.free and d + BALL_R >= R:
            ang = math.atan2(dy, dx)
            diff = abs((ang - ring + math.pi) % (2 * math.pi) - math.pi)
            window = gap / 2 - BALL_R / R
            if diff < window:
                b.free = True
                return
            nx, ny = dx / d, dy / d
            vn = b.vx * nx + b.vy * ny
            if vn > 0:
                b.vx -= 2 * vn * nx
                b.vy -= 2 * vn * ny
                sp = math.hypot(b.vx, b.vy)
                k = min(BOOST, VMAX / sp) if sp > 0 else 1
                b.vx *= k
                b.vy *= k
                self.bounces.append((t, vn))
                if diff < window + 0.13 and t - b.last_near > 2:
                    b.last_near = t
                    self.near.append((t, b.name))
            b.x = CX + nx * (R - BALL_R)
            b.y = CY + ny * (R - BALL_R)
        if b.free and b.escaped_at is None and d - BALL_R > R + 2:
            b.escaped_at = t
            self.escapes.append((t, b.name))
        if b.free and b.escaped_at is None and d + BALL_R < R - 4:
            b.free = False  # 隙間から戻ってきた

    def _collide(self):
        inside = [b for b in self.balls if b.escaped_at is None]
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

    # ----- 演出の計画 -----
    def highlights(self):
        """スローにする区間と、表示するニアミスを決める。"""
        slow, near_shown = [], []
        if self.escapes:
            for et, _ in {self.escapes[0], self.escapes[-1]}:
                slow.append((et - 0.6, et + 0.3))
        busy = [e[0] for e in self.escapes] + [tw[0] for tw in self.twists]
        for t, name in self.near:
            if len(near_shown) >= 3:
                break
            if all(abs(t - x) > 2.5 for x in busy + [n[0] for n in near_shown]):
                near_shown.append((t, name))
                slow.append((t - 0.35, t + 0.25))
        return slow, near_shown

    def score(self):
        """展開の良さ。どんでん返しやニアミス、TWIST 直後の脱出を高く評価する。"""
        n = len(CHARACTERS) + 1
        if len(self.escapes) < n:
            return -1
        ts = [e[0] for e in self.escapes]
        if not (7 <= ts[0] <= 18) or ts[-1] > 48:
            return -1
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        if min(gaps) < 2.0:
            return -1
        s = min(gaps, default=0)
        winner = self.escapes[0][1]
        if winner == MYSTERY[0]:
            s += 6                      # 乱入者が優勝する大番狂わせ
        elif self.escapes[-1][1] == MYSTERY[0]:
            s += 1
        s += min(3, len(self.near))     # ニアミスの多さ
        for tt, _ in self.twists:       # TWIST 直後に脱出が起きると「ルール変更が効いた」感が出る
            if any(0 < et - tt < 3 for et in ts):
                s += 2
        return s


def pick_seed(max_tries=400):
    best = (-1, None)
    for seed in range(max_tries):
        sim = Sim(seed).run()
        s = sim.score()
        if s > best[0]:
            best = (s, seed)
            print(f"  seed {seed}: score {s:.1f} 脱出 {[(round(t, 1), n) for t, n in sim.escapes]}", file=sys.stderr)
        if s >= 14:
            break
    if best[1] is None:
        sys.exit("条件を満たすシードが見つかりませんでした")
    return best[1]


# ---------- 時間の伸び縮み（スローモーション） ----------
def timeline(sim, slow):
    """出力フレームごとのシミュレーション時刻を作る。"""
    total = sim.states[-1][0]
    st, out = 0.0, []
    while st < total:
        out.append(st)
        f = SLOW if any(a <= st <= b for a, b in slow) else 1.0
        st += f / FPS
    return np.array(out)


def to_out(sim_times, frame_sim):
    """シミュレーション時刻 → 出力動画の時刻。"""
    return np.interp(sim_times, frame_sim, np.arange(len(frame_sim)) / FPS)


# ---------- 音 ----------
RATE = 44100


def tone(freq, dur, vol, decay=6):
    t = np.arange(int(dur * RATE)) / RATE
    env = np.minimum(1, t / 0.004) * np.exp(-t * decay)
    w = np.sin(2 * np.pi * freq * t) + 0.45 * np.sin(4 * np.pi * freq * t) + 0.2 * np.sin(6 * np.pi * freq * t)
    return w * env * vol


def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


def whoosh(dur=0.5, vol=0.5):
    n = int(dur * RATE)
    noise = np.random.default_rng(0).standard_normal(n)
    t = np.arange(n) / RATE
    sweep = np.sin(2 * np.pi * (200 + 1800 * t / dur) * t)
    return (noise * 0.4 + sweep * 0.6) * np.sin(np.pi * t / dur) * vol


def build_audio(path, sim, frame_sim, near_shown, total):
    out = np.zeros(int((total + 1) * RATE))

    def add(sig, at):
        i = int(at * RATE)
        n = min(len(sig), len(out) - i)
        if n > 0:
            out[i:i + n] += sig[:n]

    note, last = 0, -1.0
    for t, vn in sim.bounces:
        if t - last < 0.06:   # 同時に鳴りすぎないように間引く
            continue
        last = t
        add(tone(midi(MELODY[note % len(MELODY)]), 0.9, 0.35 + 0.4 * min(1, vn / 1500)), to_out(t, frame_sim))
        note += 1
    for t, _ in sim.escapes:
        for k, m in enumerate([72, 76, 79, 84]):
            add(tone(midi(m), 1.2, 0.35), to_out(t, frame_sim) + k * 0.07)
    for t, _ in sim.twists:   # TWIST: 低音の警告音 + 風切り音
        ot = to_out(t, frame_sim)
        add(tone(midi(40), 0.6, 0.7, decay=3) + tone(midi(41), 0.6, 0.5, decay=3), ot)
        add(whoosh(), ot)
    for t, _ in near_shown:   # ニアミス: 不協和音
        add(tone(midi(70), 0.6, 0.35) + tone(midi(71), 0.6, 0.35), to_out(t, frame_sim))
    for m in [57, 64, 69, 72, 76]:
        add(tone(midi(m), 2.5, 0.3), to_out(sim.end_t, frame_sim) + 0.2)
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
def mix(c, k, base=BG):
    return tuple(int(base[i] + (c[i] - base[i]) * k) for i in range(3))


def centered(d, y, text, font, fill, stroke=0):
    b = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
    d.text(((W - (b[2] - b[0])) // 2 - b[0], y), text, font=font, fill=fill,
           stroke_width=stroke, stroke_fill=(0, 0, 0))


def render(sim, frame_sim, slow, near_shown, out_path, audio_path):
    f_title = ImageFont.truetype(FONT, 78)
    f_sub = ImageFont.truetype(FONT, 46)
    f_twist = ImageFont.truetype(FONT, 72)
    f_name = ImageFont.truetype(FONT, 26)
    f_win = ImageFont.truetype(FONT, 110)
    roster = CHARACTERS + [MYSTERY]
    colors = dict(roster)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    ot_twist = [(to_out(t, frame_sim), k) for t, k in sim.twists]
    ot_esc = [(to_out(t, frame_sim), n) for t, n in sim.escapes]
    ot_near = [(to_out(t, frame_sim), n, t) for t, n in near_shown]
    ot_end = to_out(sim.end_t, frame_sim)
    shake_at = [t for t, _ in ot_twist] + [t for t, _ in ot_esc]
    shake_rng = random.Random(1)
    history = []
    for fi, st in enumerate(frame_sim):
        ot = fi / FPS
        idx = min(int(round(st / DT)), len(sim.states) - 1)
        _, ring, gap, pos = sim.states[idx]
        history.append(pos)
        is_slow = any(a <= st <= b for a, b in slow)
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        # 背景のフラッシュ（TWIST 直後）
        for t, _ in ot_twist:
            if 0 <= ot - t < 0.25:
                img.paste(mix((120, 30, 160), 1 - (ot - t) / 0.25), (0, 0, W, H))
                d = ImageDraw.Draw(img)
        # ヘッダー
        centered(d, 150, "WHICH BALL", f_title, (255, 255, 255))
        centered(d, 240, "ESCAPES FIRST?", f_title, (255, 215, 80))
        # 順位表（謎のボールは登場するまで伏せる）
        done = [e for e in ot_esc if e[0] <= ot]
        mystery_in = len(pos) > len(CHARACTERS)
        for k, (name, color) in enumerate(roster):
            cx = int(W / len(roster) * (k + 0.5))
            if name == MYSTERY[0] and not mystery_in:
                d.ellipse([cx - 22, 380, cx + 22, 424], outline=(90, 90, 110), width=3)
                b = d.textbbox((0, 0), "?", font=f_name)
                d.text((cx - (b[2] - b[0]) / 2 - b[0], 388), "?", font=f_name, fill=(90, 90, 110))
                continue
            rank = next((i + 1 for i, e in enumerate(done) if e[1] == name), None)
            d.ellipse([cx - 22, 380, cx + 22, 424], fill=color,
                      outline=(200, 200, 210) if name == MYSTERY[0] else None, width=3)
            label = name + (f"  #{rank}" if rank else "")
            b = d.textbbox((0, 0), label, font=f_name)
            d.text((cx - (b[2] - b[0]) / 2 - b[0], 436), label, font=f_name,
                   fill=(255, 255, 255) if rank else (150, 150, 165))
        # リング（隙間以外を弧で描く）
        start = math.degrees(ring + gap / 2)
        end = math.degrees(ring - gap / 2 + 2 * math.pi)
        hue = (ot * 0.05) % 1
        ring_col = tuple(int(160 + 95 * math.sin(2 * math.pi * (hue + o))) for o in (0, 1 / 3, 2 / 3))
        for wdt, k in [(26, 0.18), (14, 0.45), (8, 1.0)]:
            d.arc([CX - R - wdt // 2, CY - R - wdt // 2, CX + R + wdt // 2, CY + R + wdt // 2],
                  start, end, fill=mix(ring_col, k), width=wdt)
        # ボールと軌跡
        for i, (x, y) in enumerate(pos):
            name, color = roster[i]
            mys = name == MYSTERY[0]
            trail = [h[i] for h in history[-14:] if len(h) > i]
            for j, (px, py) in enumerate(trail[:-1]):
                k = (j + 1) / len(trail) * 0.5
                r = BALL_R * (0.4 + 0.6 * (j + 1) / len(trail))
                d.ellipse([px - r, py - r, px + r, py + r], fill=mix((200, 200, 220) if mys else color, k * (0.6 if mys else 1)))
            d.ellipse([x - BALL_R - 8, y - BALL_R - 8, x + BALL_R + 8, y + BALL_R + 8],
                      fill=mix((200, 200, 220) if mys else color, 0.3))
            d.ellipse([x - BALL_R, y - BALL_R, x + BALL_R, y + BALL_R], fill=color,
                      outline=(230, 230, 240) if mys else None, width=4)
            if mys:
                b = d.textbbox((0, 0), "?", font=f_sub)
                d.text((x - (b[2] - b[0]) / 2 - b[0], y - (b[3] - b[1]) / 2 - b[1]), "?", font=f_sub, fill=(255, 255, 255))
            b = d.textbbox((0, 0), name, font=f_name)
            d.text((x - (b[2] - b[0]) / 2, y - BALL_R - 38), name, font=f_name, fill=(235, 235, 245))
        # ニアミス
        for t, name, st_near in ot_near:
            if 0 <= ot - t < 1.0:
                i = [r[0] for r in roster].index(name)
                x, y = pos[i]
                b = d.textbbox((0, 0), "SO CLOSE!", font=f_sub, stroke_width=4)
                tx = min(max(x - (b[2] - b[0]) / 2, 20), W - (b[2] - b[0]) - 20)
                d.text((tx, y - BALL_R - 100), "SO CLOSE!", font=f_sub, fill=(255, 90, 90),
                       stroke_width=4, stroke_fill=(0, 0, 0))
        # TWIST バナー
        for t, kind in ot_twist:
            if 0 <= ot - t < 1.6:
                y0 = 485
                d.rectangle([0, y0 - 20, W, y0 + 130], fill=(150, 30, 190))
                centered(d, y0 - 5, "TWIST!", f_sub, (255, 230, 120))
                centered(d, y0 + 45, TWISTS[kind], f_twist, (255, 255, 255), stroke=3)
        # 脱出の瞬間テロップ
        for k, (t, name) in enumerate(ot_esc):
            if 0 <= ot - t < 1.4:
                label = "UPSET!!  " if name == MYSTERY[0] and k == 0 else ""
                ordinal = ["1ST", "2ND", "3RD", "4TH", "5TH"][k]
                centered(d, 1600, f"{label}{name} ESCAPED! {ordinal}", f_sub, colors[name] if name != "???" else (255, 255, 255), stroke=3)
        if is_slow:
            d.text((40, 490), "SLOW-MO", font=f_name, fill=(255, 90, 90))
        if ot < ot_end:
            centered(d, 1700, "Comment your pick!", f_sub, (170, 170, 190))
        # エンディング
        if ot >= ot_end + 0.2 and sim.escapes:
            name = sim.escapes[0][1]
            img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), min(0.75, (ot - ot_end) * 1.5))
            d = ImageDraw.Draw(img)
            mys = name == MYSTERY[0]
            centered(d, 700, "NOBODY SAW THAT COMING..." if mys else "WINNER", f_sub, (255, 255, 255))
            centered(d, 790, "MYSTERY BALL" if mys else name, f_win, (230, 230, 240) if mys else colors[name])
            centered(d, 970, "Did you guess right?", f_sub, (220, 220, 230))
            centered(d, 1050, "Follow for the next race!", f_sub, (255, 215, 80))
        # 画面シェイク
        amp = max([18 * (1 - (ot - t) / 0.35) for t in shake_at if 0 <= ot - t < 0.35], default=0)
        if amp > 0:
            dx, dy = shake_rng.uniform(-amp, amp), shake_rng.uniform(-amp, amp)
            shaken = Image.new("RGB", (W, H), BG)
            shaken.paste(img, (int(dx), int(dy)))
            img = shaken
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
    sim = Sim(seed).run()
    slow, near_shown = sim.highlights()
    frame_sim = timeline(sim, slow)
    total = len(frame_sim) / FPS
    print(f"seed={seed} 長さ={total:.1f}s")
    print(f"  TWIST: {[(round(t, 1), k) for t, k in sim.twists]}")
    print(f"  脱出: {[(round(t, 1), n) for t, n in sim.escapes]}")
    print(f"  ニアミス: {[(round(t, 1), n) for t, n in near_shown]}")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        build_audio(wav, sim, frame_sim, near_shown, total)
        render(sim, frame_sim, slow, near_shown, args.output, wav)
    print(f"作成しました: {args.output}")


if __name__ == "__main__":
    main()
