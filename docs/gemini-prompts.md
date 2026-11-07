# Gemini アプリ用プロンプト（犬猫キャラクター素材）

すべて**同じチャット**で、上から順に送る。英語のまま貼り付ける。

## 共通スタイル（各プロンプトの末尾に含めてある）
cute chibi mascot style, flat vector illustration, thick dark brown outline, simple cel shading,
big glossy eyes, head only (no body), front view, round head, solid pure green background (#00FF00),
no text, no logo, original design

## STEP 1: 5体の顔ぶれ（1枚）
```
Create a character lineup of 5 original animal mascot heads in a single row, evenly spaced, all the same size, not overlapping:
1) MOCHI - a shiba inu: orange-tan fur, cream-white cheeks and muzzle, two small cream eyebrow dots, pointy upright ears.
2) BISCUIT - a beagle: tan face with a white stripe down the middle of the forehead, long floppy dark brown ears.
3) GINGER - an orange tabby cat: bright orange fur with darker orange stripes on the forehead, pink inner ears.
4) LUNA - a blue-gray cat: soft blue-gray fur, white muzzle, pink inner ears.
5) A mysterious black cat: jet-black fur, glowing yellow eyes, slightly mischievous look.
Style: cute chibi mascot style, flat vector illustration, thick dark brown outline, simple cel shading, big glossy eyes, head only (no body), front view, round head, solid pure green background (#00FF00), no text, no logo, original design.
```

## STEP 2: キャラごとの表情シート（5枚）
`[NAME]` と `[N]` を差し替えて5回送る。
（MOCHI=1, BISCUIT=2, GINGER=3, LUNA=4, black cat=5）

```
Using exactly the same character design and style as character #[N] ([NAME]) in the lineup above, create an expression sheet in a 2x2 grid. Each head is the same size, centered in its cell, with wide empty space between cells:
- top-left: normal, calm happy smile
- top-right: panicked, wide open eyes with small pupils, small open mouth, a blue sweat drop
- bottom-left: crying loudly, eyes squeezed shut, streams of blue tears, wide open mouth
- bottom-right: overjoyed, eyes closed in an upward curve, big open smiling mouth, pink blush
Style: cute chibi mascot style, flat vector illustration, thick dark brown outline, simple cel shading, head only (no body), front view, round head, solid pure green background (#00FF00), no text, no logo.
```

## コツ
- 背景を緑にしているのは、切り抜きをきれいにするため（キャラクターに緑色が使われていないので）
- キャラクターの見た目がずれたら、STEP 1 の画像を添付して「この画像の #N と同じキャラで」と指示し直す
- 有名キャラクターに似てしまったら作り直す（収益化のため）
- 画像は元の解像度のままダウンロードして送る（スクリーンショットは避ける）
