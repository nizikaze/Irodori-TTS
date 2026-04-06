# フォーク運用メモ

## リモート構成

```
origin    https://github.com/nizikaze/Irodori-TTS.git   ← 自分のフォーク
upstream  https://github.com/Aratako/Irodori-TTS.git    ← 本家
```

## 本家の更新を取り込む

```bash
git fetch upstream
git rebase upstream/main
```

## 自分のコードをpush

```bash
git push origin main
```

---

## ディレクトリ構造方針

```
Irodori-TTS/
├── irodori_tts/          # 本家ライブラリ（基本触らない）
├── gradio_app.py         # 本家
├── gradio_app_voicedesign.py  # 本家
│
└── my/                   # 自分のコードはここ
    ├── scripts/          # 自作スクリプト（推論・バッチ処理など）
    ├── gradio/           # 本家UIを改造したもの
    ├── configs/          # 自分用の設定ファイル
    └── docs/             # このメモなど
```

## 本家ファイルを書き換えたい場合

直接編集せず、`my/` 側で本家の関数をimportしてラップする。

```python
# my/gradio/my_app.py
from gradio_app_voicedesign import _build_runtime_key  # 本家の関数をそのまま使う

# 自分の改造を加える
```

こうすることで `git rebase upstream/main` 時にコンフリクトが起きにくくなる。
