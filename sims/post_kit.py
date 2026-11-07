#!/usr/bin/env python3
"""投稿用の一式（サムネイル画像・タイトル・説明文・ハッシュタグ）を作る。

    python3 sims/post_kit.py --seed 177 --episode 1 --out output/ep001

出力:
    <out>_thumb.png  … 1080x1920 の縦型サムネイル（Shorts / Reels / TikTok のカバー用）
    <out>_post.txt   … タイトル案・説明文・ハッシュタグ（英語メイン + 日本語）
結果のネタバレ（誰が勝つか）はタイトルにもサムネイルにも入れない。
"""
import argparse
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import escape as E  # noqa: E402
import pets as P  # noqa: E402

W, H = 1080, 1920
F = E.FONT


def thumbnail(path, seed):
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), (14, 14, 24))
    # 背景の放射グラデーション
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W / 2 - 700, 1050 - 700, W / 2 + 700, 1050 + 700], fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(Image.new("RGB", (W, H), (70, 30, 120)), img, glow)
    d = ImageDraw.Draw(img)
    # リング（隙間つき）
    cx, cy, R = W / 2, 1060, 440
    for wdt, col in [(40, (90, 50, 140)), (22, (170, 100, 255)), (12, (235, 210, 255))]:
        d.arc([cx - R, cy - R, cx + R, cy + R], -60, 240, fill=col, width=wdt)
    # 焦り顔の4体 + 隙間にいる謎のシルエット
    spots = [(-200, -120), (190, -160), (-170, 190), (200, 160)]
    for (name, kind, team, _), (dx, dy) in zip(P.CAST, spots):
        sp = P.sprite(name, kind, "panic", 120).rotate(rng.uniform(-14, 14), resample=Image.BICUBIC)
        img.paste(sp, (int(cx + dx - sp.width / 2), int(cy + dy - sp.height / 2)), sp)
    gx, gy = cx + R * math.cos(math.radians(-90)), cy + R * math.sin(math.radians(-90))
    sil = P.sprite(P.STRAY[0], P.STRAY[1], "normal", 95)
    dark = Image.new("RGBA", sil.size, (10, 10, 14, 255))
    dark.putalpha(sil.getchannel("A"))
    img.paste(dark, (int(gx - sil.width / 2), int(gy - sil.height / 2)), dark)
    d = ImageDraw.Draw(img)
    f_q = ImageFont.truetype(F, 110)
    E.centered(d, int(gy - 70), "?", f_q, (255, 230, 120), stroke=6)
    # 文字
    f_big = ImageFont.truetype(F, 128)
    f_mid = ImageFont.truetype(F, 92)
    f_small = ImageFont.truetype(F, 58)
    parts = [("DOGS", P.TEAM_COL["DOGS"]), (" vs ", (255, 255, 255)), ("CATS", P.TEAM_COL["CATS"])]
    widths = [d.textlength(t, font=f_big) for t, _ in parts]
    x = (W - sum(widths)) / 2
    for (t, c), w in zip(parts, widths):
        d.text((x, 120), t, font=f_big, fill=c, stroke_width=8, stroke_fill=(0, 0, 0))
        x += w
    E.centered(d, 285, "WHO ESCAPES", f_mid, (255, 255, 255), stroke=6)
    E.centered(d, 380, "FIRST?", f_mid, (255, 215, 80), stroke=6)
    d.rounded_rectangle([90, 1610, W - 90, 1730], radius=30, fill=(150, 30, 190))
    E.centered(d, 1635, "WAIT FOR THE TWIST...", f_small, (255, 255, 255), stroke=3)
    img.save(path)


def post_text(path, episode):
    names = ", ".join(n for n, *_ in P.CAST)
    text = f"""==== タイトル案（英語・どれか1つ）====
Dogs vs Cats: Who Escapes First? 🐶🐱 #{episode}
Team Dogs or Team Cats? Only ONE escapes first... 😱
I didn't expect THIS ending 😳 Dogs vs Cats Escape Race

==== 説明文 ====
Dogs vs Cats escape race #{episode}! 🐶🐱
{names} race to escape the spinning ring... but watch out for the TWIST!
Who did you pick? Comment your team below 👇
Follow for the next race and see which team takes the lead!

ドッグス vs キャッツ 脱出レース 第{episode}戦！
どっちのチームを応援する？コメントで教えてね👇

==== ハッシュタグ ====
#shorts #dogsvscats #satisfying #simulation #cat #dog #cute #animation #catsofyoutube #dogsofyoutube

==== 投稿メモ ====
- サムネイル: *_thumb.png をカバー画像に設定（YouTube ショートはアプリのアップロード画面で選択）
- 固定コメント: "Who did you pick? 🐶 or 🐱"（コメント数が伸びやすい）
- AI 表示ラベル: 写実的な映像ではないアニメなので、YouTube の「改変・合成コンテンツ」申告は原則不要
- 同じ動画を TikTok / Instagram リールにも投稿（透かしのない元ファイルを使う）
"""
    Path(path).write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--out", default="output/ep001")
    args = ap.parse_args()
    thumbnail(f"{args.out}_thumb.png", args.seed)
    post_text(f"{args.out}_post.txt", args.episode)
    print(f"作成しました: {args.out}_thumb.png, {args.out}_post.txt")


if __name__ == "__main__":
    main()
