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
