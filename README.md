# 動画作成ツール

シーンを JSON で書くだけで、テロップ付きの MP4 動画（1280x720 / H.264 + AAC）を作成します。

## 使い方

```bash
python3 make_video.py examples/sample.json -o sample.mp4
```

必要なもの: Python 3、Pillow、numpy、ffmpeg

## JSON の書き方

```json
{
  "width": 1280, "height": 720, "fps": 30,
  "audio": "bgm",
  "scenes": [
    {"title": "タイトル", "subtitle": "サブタイトル", "duration": 4, "bg": ["#1e3c72", "#2a5298"]}
  ]
}
```

| キー | 説明 |
|---|---|
| `audio` | `"bgm"` で自動生成の BGM、音声ファイルのパスでその音源、省略で無音 |
| `font` | フォントファイルのパス（省略時は IPA ゴシックなどを自動検索） |
| `fade` | シーン切り替えのフェード秒数（初期値 0.6） |
| `scenes[].title` / `subtitle` | 表示するテキスト |
| `scenes[].duration` | シーンの秒数 |
| `scenes[].bg` | 背景グラデーションの 2 色 |
| `scenes[].color` | 文字色（初期値 `#FFFFFF`） |

## ショート試作: Which ball escapes first?

```bash
python3 sims/escape.py -o output/escape.mp4            # 展開が良くなるシードを自動選択
python3 sims/escape.py --seed 48 -o output/escape.mp4  # シード固定で再現（output/escape_twist.mp4）
```

- 縦型 1080x1920 / 60fps。回転リングの隙間（時間とともに広がる）から4体のキャラクターボールが脱出を競う
- リングに当たるたびに「エリーゼのために」（パブリックドメイン）が1音ずつ鳴る。音はすべて自前で合成
- キャラクター・メロディ・物理パラメータは `sims/escape.py` 冒頭の定数で変更できる
- 意外性の仕掛け: TWIST イベント（逆回転・重力反転・高速回転・謎のボール乱入）、ニアミス時の「SO CLOSE!」スロー、脱出時のスロー + 画面シェイク。シード選びでは乱入者の優勝などのどんでん返しを優先する

## ショート試作: DOGS vs CATS（犬猫キャラクター版）

```bash
python3 sims/pets.py -o output/pets.mp4                 # 展開の良いシードを自動選択
python3 sims/pets.py --winner cats -o output/pets.mp4   # 優勝チームを指定（dogs / cats / stray）
python3 sims/characters.py output/characters.png        # キャラクター表情シートを出力
```

- 犬チーム（MOCHI＝柴犬、BISCUIT＝ビーグル）vs 猫チーム（GINGER＝茶トラ、LUNA＝グレー）＋乱入する黒猫（???）
- キャラクターはすべてコードで描いたオリジナル（`sims/characters.py`）。表情は通常・焦り・泣き・喜びの4種類で、状況に応じて自動で切り替わる
- 脱出時と優勝発表に合成した鳴き声（ワンワン／ニャー）が入る

### 画像素材（Gemini アプリなどで作成）の取り込み

```bash
python3 sims/import_sprites.py lineup assets/source/lineup.jpg MOCHI BISCUIT GINGER LUNA STRAY
python3 sims/import_sprites.py sheet assets/source/mochi.jpg MOCHI   # 2x2 表情シート
python3 sims/import_sprites.py cells assets/source/luna.jpg LUNA 3x2 normal=0,0 panic=1,0 cry=0,1 happy=1,1   # 崩れた配置のシート
```

黒猫の瞳は `python3 sims/recolor_eyes.py assets/sprites/STRAY_normal.png` で茶色→黄色に塗り替えている。

`assets/sprites/<NAME>_<expr>.png` があれば `pets.py` はそれを使う（表情の画像がなければ normal で代用、画像がなければコード描画）。プロンプトは `docs/gemini-prompts.md`。

### 投稿用の一式

```bash
python3 sims/pets.py --seed 177 -o output/ep001.mp4
python3 sims/post_kit.py --seed 177 --episode 1 --out output/ep001   # サムネイル + タイトル・説明文・ハッシュタグ
```

- 物理はゆっくりめ（キャラの表情が追える速さ）で、動画は 40 秒前後に収まる展開を選ぶ
- キャラクターにはチーム色（犬=オレンジ、猫=水色）の縁取りが付く
