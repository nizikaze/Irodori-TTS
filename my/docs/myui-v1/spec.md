# myui-v1 仕様書

## 概要

`gradio_app_voicedesign.py` を改造・拡張した独自UI。  
生成UIと閲覧UIを分離し、SQLiteで永続管理する。

---

## ファイル構成

| ファイル | フレームワーク | 役割 |
|---|---|---|
| `my/gradio_gen.py` | Gradio | 生成UI → SQLite書き込み |
| `my/streamlit_history.py` | Streamlit | SQLite読み取り・閲覧・編集 |
| `my/db.py` | - | SQLite共通ロジック |
| `my/data/generations.db` | SQLite | DBファイル本体 |

---

## DBスキーマ

```sql
CREATE TABLE generations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    text              TEXT NOT NULL,
    caption           TEXT,
    seed              INTEGER,
    num_steps         INTEGER,
    cfg_scale_text    REAL,
    cfg_scale_caption REAL,
    cfg_guidance_mode TEXT,
    checkpoint        TEXT,
    file_path         TEXT NOT NULL,
    favorite          INTEGER DEFAULT 0,   -- 0/1
    rating            INTEGER,             -- 1〜5 or NULL
    note              TEXT                 -- メモ
);

CREATE TABLE tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE generation_tags (
    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    tag_id        INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (generation_id, tag_id)
);
```

---

## 生成UI（Gradio）

### 変更点（gradio_app_voicedesign.py からの差分）

- **generate_forever モード**: ジェネレータ関数で無限ループ生成。Gradio が自動でStopボタンを表示。
- **自動再生**: 最新の1件のみ `autoplay=True`
- **直近N件の履歴表示**: `gr.State` で直近5件のファイルパスを保持し、Audio×5で表示
- **候補グリッド削除**: num_candidatesスライダーおよび32候補グリッドを廃止
- **生成完了時にSQLiteへ書き込み**: 生成パラメータ・ファイルパスを記録

### ファイル名規則

```
{YYYYMMDD_HHMMSS}_{seed}.wav
```

---

## 閲覧UI（Streamlit）

### 機能

- **一覧表示**: 生成サンプルをカード形式で複数同時表示
- **オーディオ再生**: 各カードに `st.audio` を配置（複数同時表示可）
- **表示情報**: text / caption / seed / num_steps / checkpoint / 生成日時
- **フィルター・検索**: text / caption のキーワード検索、お気に入りのみ表示
- **ソート**: 新しい順 / レーティング順 / お気に入り順
- **レーティング**: 1〜5で評価
- **お気に入り**: トグル
- **メモ**: 自由記述
- **タグ**: 将来実装（生成UI・閲覧UI両方。DBスキーマは `tags` / `generation_tags` テーブルとして先行定義済み）

---
