# Irodori-TTS — Fork by nizikaze

本家リポジトリ [Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS) のフォークです。
本家の使い方・モデル情報はルートの [README.md](../README.md) を参照してください。

## このフォークについて

本家コードを壊さずに自分の実験・改造を重ねるため、独自コードはすべて `my/` ディレクトリ以下に置いています。

## ディレクトリ構成

```
my/
├── README.md              # このファイル
├── db.py                  # 生成履歴SQLiteモジュール
├── gradio_gen.py          # 独自生成UI（Gradio）
├── streamlit_history.py   # 生成履歴の閲覧・編集UI（Streamlit）
├── run_gen.sh             # 生成UI起動スクリプト
├── data/
│   ├── generations.db     # 生成履歴DB（自動生成）
│   └── outputs/           # 生成した wav ファイル（自動生成）
└── docs/
    ├── fork-workflow.md
    └── myui-v1/
        ├── spec.md        # 仕様書
        └── TODO.md        # 実装TODO
```

## 運用方針

- 本家ファイルは原則変更しない
- 本家の関数を使いたい場合は `my/` 側でimportしてラップする
- 本家の更新取り込みは `git fetch upstream && git rebase upstream/main`

詳細は [my/docs/fork-workflow.md](docs/fork-workflow.md) を参照。

## 独自UIの起動方法

### 生成UI（Gradio）

**簡単起動:** `my/run_gen.sh` を実行 → サーバー起動後にブラウザが自動で開きます。

コマンドラインから起動する場合:

```bash
# リポジトリルートで実行
python -m my.gradio_gen
```

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--server-name` | `127.0.0.1` | バインドするホスト名 |
| `--server-port` | `7862` | ポート番号 |
| `--share` | OFF | Gradio の公開リンクを生成 |
| `--debug` | OFF | デバッグモードで起動 |

起動後、ブラウザで `http://127.0.0.1:7862` にアクセスしてください。

#### 本家UIとの主な違い

- **候補グリッド廃止**: 常に1件ずつ生成（32枠のグリッドなし）
- **履歴表示**: 直近5件の生成結果を画面上部に表示
- **Autoplay**: ONにすると最新の生成結果を自動再生
- **Forever モード**: 「Generate Forever」ボタンで連続生成、「Cancel Forever」ボタンで停止。稼働中はスピナーアイコンが表示される
- **DB 記録**: 生成のたびに SQLite に履歴を保存（`my/data/generations.db`）
- **ファイル名**: `{YYYYMMDD_HHMMSS}_{seed}.wav` 形式で `my/data/outputs/` に保存

### 閲覧UI（Streamlit）

生成履歴の一覧表示・検索・編集ができるUI。

**簡単起動:** `my/run_history.sh` を実行 → サーバー起動後にブラウザが自動で開きます。

コマンドラインから起動する場合:

```bash
# リポジトリルートで実行
streamlit run my/streamlit_history.py
```

起動後、ブラウザで `http://localhost:8502` にアクセスしてください。

#### 主な機能

- **カード形式の一覧表示**: 各レコードのテキスト・キャプション・メタ情報を表示
- **音声再生**: 各カードに `st.audio` を配置、複数同時表示可能
- **キーワード検索**: text / caption の部分一致検索（サイドバー）
- **フィルター**: お気に入りのみ表示
- **ソート**: 新しい順 / 古い順 / レーティング順 / お気に入り優先
- **編集機能**: レーティング（1〜5）、お気に入りトグル、メモ入力（各カードの「✏️ 編集」から）

## 独自の変更・追加機能

| 機能 | 概要 | ファイル |
|------|------|------|
| 生成履歴DB | 生成パラメータ・ファイルパスをSQLiteに永続化 | `my/db.py` |
| 独自生成UI | 履歴表示・autoplay・連続生成に対応したGradio UI | `my/gradio_gen.py` |
| 閲覧UI | 生成履歴の一覧表示・検索・レーティング・お気に入り・メモ編集 | `my/streamlit_history.py` |
