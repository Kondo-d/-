#!/usr/bin/env python3
"""「DOGS vs CATS: Who escapes first?」縦型ショートを生成する。

物理・演出の仕組みは escape.py を流用し、ボールを犬猫キャラクターに置き換える。
キャラクターは状況に応じて表情が変わる（通常・焦り・泣き・喜び）。

使い方:
    python3 sims/pets.py -o output/pets.mp4                  # 展開の良いシードを自動選択
    python3 sims/pets.py --winner cats -o output/pets.mp4    # 優勝チームを指定（dogs/cats/stray）
    python3 sims/pets.py --seed 48 -o output/pets.mp4        # シード固定
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

sys.path.insert(0, str(Path(__file__).parent))
import escape as E  # noqa: E402
from characters import draw  # noqa: E402

# ---------- キャラクター設定 ----------
# (名前, 種類, チーム, 軌跡の色)
CAST = [
    ("MOCHI", "shiba", "DOGS", (240, 160, 90)),
    ("BISCUIT", "beagle", "DOGS", (200, 130, 80)),
    ("GINGER", "tabby", "CATS", (250, 170, 80)),
    ("LUNA", "gray", "CATS", (160, 175, 210)),
]
STRAY = ("???", "black", "STRAY", (150, 150, 175))
TEAM_COL = {"DOGS": (255, 170, 70), "CATS": (120, 190, 255), "STRAY": (230, 230, 240)}

E.BALL_R = 50
E.GAP0 = 0.34
E.CHARACTERS = [(n, c) for n, _, _, c in CAST]
E.MYSTERY = (STRAY[0], STRAY[3])
E.TWISTS["MYSTERY"] = "A STRAY CAT APPEARS!"

ROSTER = CAST + [STRAY]
INFO = {n: (k, t, c) for n, k, t, c in ROSTER}
W, H, FPS, BG = E.W, E.H, E.FPS, E.BG


# ---------- シード選び ----------
def pick_seed(winner, max_tries=500):
    best = (-1, None)
    for seed in range(max_tries):
        sim = E.Sim(seed).run()
        s = sim.score()
        if s < 0:
            continue
        team = INFO[sim.escapes[0][1]][1]
        if winner and team != winner.upper():
            continue
        if team == "STRAY" and not winner:
            s -= 6   # 乱入者の優勝ばかりにならないよう、指定なしの時はボーナスを外す
        if s > best[0]:
            best = (s, seed)
            print(f"  seed {seed}: score {s:.1f} 優勝 {sim.escapes[0][1]}", file=sys.stderr)
        if s >= 10:
            break
    if best[1] is None:
        sys.exit("条件を満たすシードが見つかりませんでした")
    return best[1]


# ---------- 鳴き声（合成） ----------
RATE = 44100


def meow(vol=0.6):
    dur = 0.55
    t = np.arange(int(dur * RATE)) / RATE
    f0 = np.interp(t, [0, 0.12, 0.3, dur], [520, 820, 700, 430])
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    bright = np.interp(t, [0, 0.15, dur], [0.3, 1.0, 0.25])   # 「ミ→ャ→ウ」の口の開き
    sig = sum((bright ** (k - 1)) / k * np.sin(k * phase) for k in range(1, 9))
    env = np.minimum(1, t / 0.04) * np.minimum(1, (dur - t) / 0.12)
    return sig * env * vol


def bark(vol=0.7):
    out = []
    for _ in range(2):
        dur = 0.16
        t = np.arange(int(dur * RATE)) / RATE
        f0 = np.interp(t, [0, 0.03, dur], [380, 330, 200])
        phase = 2 * np.pi * np.cumsum(f0) / RATE
        sig = sum(np.sin(k * phase) / k ** 0.8 for k in range(1, 12))
        sig += np.random.default_rng(3).standard_normal(len(t)) * 0.6
        env = np.minimum(1, t / 0.008) * np.exp(-t * 14)
        out += [sig * env * vol, np.zeros(int(0.07 * RATE))]
    return np.concatenate(out)


def build_audio(path, sim, frame_sim, near_shown, total):
    E.build_audio(path, sim, frame_sim, near_shown, total)
    with wave.open(str(path)) as wf:
        base = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(float) / 32767

    def add(sig, at):
        i = int(at * RATE)
        n = min(len(sig), len(base) - i)
        if n > 0:
            base[i:i + n] += sig[:n]

    for t, name in sim.escapes:
        team = INFO[name][1]
        add(bark() if team == "DOGS" else meow(), E.to_out(t, frame_sim) + 0.25)
    winner_team = INFO[sim.escapes[0][1]][1] if sim.escapes else None
    if winner_team:
        add(bark(0.8) if winner_team == "DOGS" else meow(0.8), E.to_out(sim.end_t, frame_sim) + 0.6)
    base = base / (np.abs(base).max() or 1) * 0.9
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(RATE)
        wf.writeframes((base * 32767).astype(np.int16).tobytes())


# ---------- 描画 ----------
def paste_center(img, sprite, x, y):
    img.paste(sprite, (int(x - sprite.width / 2), int(y - sprite.height / 2)), sprite)


def render(sim, frame_sim, slow, near_shown, out_path, audio_path):
    F = E.FONT
    f_title = ImageFont.truetype(F, 84)
    f_title2 = ImageFont.truetype(F, 64)
    f_sub = ImageFont.truetype(F, 46)
    f_twist = ImageFont.truetype(F, 66)
    f_name = ImageFont.truetype(F, 28)
    f_win = ImageFont.truetype(F, 96)
    r = E.BALL_R
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    to_out = lambda t: float(E.to_out(t, frame_sim))  # noqa: E731
    ot_twist = [(to_out(t), k) for t, k in sim.twists]
    ot_esc = [(to_out(t), n) for t, n in sim.escapes]
    ot_near = [(to_out(t), n) for t, n in near_shown]
    ot_end = to_out(sim.end_t)
    esc_at = {n: t for t, n in ot_esc}
    shake_at = [t for t, _ in ot_twist] + [t for t, _ in ot_esc]
    shake_rng = random.Random(1)
    history = []
    winner = sim.escapes[0][1] if sim.escapes else None
    for fi, st in enumerate(frame_sim):
        ot = fi / FPS
        idx = min(int(round(st / E.DT)), len(sim.states) - 1)
        _, ring, gap, pos = sim.states[idx]
        prev = history[-1] if history else pos
        history.append(pos)
        is_slow = any(a <= st <= b for a, b in slow)
        recent_twist = any(0 <= ot - t < 1.2 for t, _ in ot_twist)
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        for t, _ in ot_twist:
            if 0 <= ot - t < 0.25:
                img.paste(E.mix((120, 30, 160), 1 - (ot - t) / 0.25), (0, 0, W, H))
                d = ImageDraw.Draw(img)
        # ヘッダー: DOGS vs CATS
        parts = [("DOGS", TEAM_COL["DOGS"]), (" vs ", (255, 255, 255)), ("CATS", TEAM_COL["CATS"])]
        widths = [d.textlength(p, font=f_title) for p, _ in parts]
        x = (W - sum(widths)) / 2
        for (p, c), w in zip(parts, widths):
            d.text((x, 130), p, font=f_title, fill=c)
            x += w
        E.centered(d, 235, "WHO ESCAPES FIRST?", f_title2, (255, 215, 80))
        # 順位表
        done = [e for e in ot_esc if e[0] <= ot]
        stray_in = len(pos) > len(CAST)
        for k, (name, kind, team, _) in enumerate(ROSTER):
            cx = int(W / len(ROSTER) * (k + 0.5))
            if name == STRAY[0] and not stray_in:
                d.ellipse([cx - 26, 372, cx + 26, 424], outline=(90, 90, 110), width=3)
                b = d.textbbox((0, 0), "?", font=f_name)
                d.text((cx - (b[2] - b[0]) / 2 - b[0], 384), "?", font=f_name, fill=(90, 90, 110))
                continue
            rank = next((i + 1 for i, e in enumerate(done) if e[1] == name), None)
            paste_center(img, draw(kind, "happy" if rank else "normal", 26), cx, 398)
            label = name + (f" #{rank}" if rank else "")
            b = d.textbbox((0, 0), label, font=f_name)
            d.text((cx - (b[2] - b[0]) / 2 - b[0], 442), label, font=f_name,
                   fill=TEAM_COL[team] if rank else (150, 150, 165))
        # リング
        start = math.degrees(ring + gap / 2)
        end = math.degrees(ring - gap / 2 + 2 * math.pi)
        hue = (ot * 0.05) % 1
        ring_col = tuple(int(160 + 95 * math.sin(2 * math.pi * (hue + o))) for o in (0, 1 / 3, 2 / 3))
        R = E.R
        for wdt, kk in [(26, 0.18), (14, 0.45), (8, 1.0)]:
            d.arc([E.CX - R - wdt // 2, E.CY - R - wdt // 2, E.CX + R + wdt // 2, E.CY + R + wdt // 2],
                  start, end, fill=E.mix(ring_col, kk), width=wdt)
        # 軌跡
        for i, (x, y) in enumerate(pos):
            color = ROSTER[i][3]
            trail = [h[i] for h in history[-12:] if len(h) > i]
            for j, (px, py) in enumerate(trail[:-1]):
                kk = (j + 1) / len(trail) * 0.45
                rr = r * (0.3 + 0.5 * (j + 1) / len(trail))
                d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=E.mix(color, kk))
        # キャラクター本体
        for i, (x, y) in enumerate(pos):
            name, kind, team, _ = ROSTER[i]
            if name in esc_at and ot >= esc_at[name]:
                expr = "happy"
            elif any(n == name and 0 <= ot - t < 1.4 for t, n in ot_near):
                expr = "cry"
            else:
                dx, dy = x - E.CX, y - E.CY
                diff = abs((math.atan2(dy, dx) - ring + math.pi) % (2 * math.pi) - math.pi)
                near_gap = math.hypot(dx, dy) > R - 3 * r and diff < gap / 2 + 0.35
                expr = "panic" if (recent_twist or is_slow or near_gap) else "normal"
            vx = (x - prev[i][0]) if i < len(prev) else 0
            tilt = max(-18, min(18, -vx * 0.9))
            sp = draw(kind, expr, r).rotate(tilt, resample=Image.BICUBIC)
            paste_center(img, sp, x, y)
            b = d.textbbox((0, 0), name, font=f_name)
            d.text((x - (b[2] - b[0]) / 2, y - r * 1.9 - 20), name, font=f_name, fill=TEAM_COL[team],
                   stroke_width=3, stroke_fill=(0, 0, 0))
        # ニアミス
        for t, name in ot_near:
            if 0 <= ot - t < 1.0:
                x, y = pos[[n for n, *_ in ROSTER].index(name)]
                b = d.textbbox((0, 0), "SO CLOSE!", font=f_sub, stroke_width=4)
                tx = min(max(x - (b[2] - b[0]) / 2, 20), W - (b[2] - b[0]) - 20)
                d.text((tx, y - r * 2 - 90), "SO CLOSE!", font=f_sub, fill=(255, 90, 90),
                       stroke_width=4, stroke_fill=(0, 0, 0))
        # TWIST バナー
        for t, kind in ot_twist:
            if 0 <= ot - t < 1.6:
                y0 = 520
                d.rectangle([0, y0 - 20, W, y0 + 125], fill=(150, 30, 190))
                E.centered(d, y0 - 8, "TWIST!", f_sub, (255, 230, 120))
                E.centered(d, y0 + 42, E.TWISTS[kind], f_twist, (255, 255, 255), stroke=3)
        # 脱出テロップ
        for k, (t, name) in enumerate(ot_esc):
            if 0 <= ot - t < 1.4:
                label = "UPSET!!  " if name == STRAY[0] and k == 0 else ""
                ordinal = ["1ST", "2ND", "3RD", "4TH", "5TH"][k]
                E.centered(d, 1600, f"{label}{name} ESCAPED! {ordinal}", f_sub, TEAM_COL[INFO[name][1]], stroke=3)
        if is_slow:
            d.text((40, 495), "SLOW-MO", font=f_name, fill=(255, 90, 90))
        if ot < ot_end:
            E.centered(d, 1700, "Dog team or cat team?", f_sub, (170, 170, 190))
        # エンディング
        if ot >= ot_end + 0.2 and winner:
            img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), min(0.78, (ot - ot_end) * 1.5))
            d = ImageDraw.Draw(img)
            kind, team, _ = INFO[winner]
            pop = min(1.0, (ot - ot_end - 0.2) * 3)
            bounce = 1 + 0.08 * math.sin(min(1, pop) * math.pi)
            paste_center(img, draw(kind, "happy", int(120 * pop * bounce) or 1), W / 2, 700)
            if team == "STRAY":
                E.centered(d, 900, "NOBODY SAW THAT COMING...", f_sub, (255, 255, 255))
                E.centered(d, 970, "THE STRAY WINS?!", f_win, TEAM_COL[team])
            else:
                E.centered(d, 900, f"{winner} ESCAPED FIRST!", f_sub, (255, 255, 255))
                E.centered(d, 970, f"TEAM {team} WIN!", f_win, TEAM_COL[team])
            E.centered(d, 1140, "Did you guess right?", f_sub, (220, 220, 230))
            E.centered(d, 1220, "Follow for the next race!", f_sub, (255, 215, 80))
        # 画面シェイク
        amp = max([18 * (1 - (ot - t) / 0.35) for t in shake_at if 0 <= ot - t < 0.35], default=0)
        if amp > 0:
            shaken = Image.new("RGB", (W, H), BG)
            shaken.paste(img, (int(shake_rng.uniform(-amp, amp)), int(shake_rng.uniform(-amp, amp))))
            img = shaken
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg でエラーが発生しました")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default="pets.mp4")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--winner", choices=["dogs", "cats", "stray"])
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else pick_seed(args.winner)
    sim = E.Sim(seed).run()
    slow, near_shown = sim.highlights()
    frame_sim = E.timeline(sim, slow)
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
