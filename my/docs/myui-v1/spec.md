# myui-v1 仕様書

## 概要

`gradio_app_voicedesign.py` を改造・拡張した独自UI。  
生成UIと閲覧UIを分離し、SQLiteで永続管理する。

---

## ファイル構成

| ファイル | フレームワーク | 役割 |
|---|---|---|
| `my/gradio_gen.py` | Gradio | 生成UI（VoiceDesign版）→ SQLite書き込み |
| `my/gradio_ref.py` | Gradio | 生成UI（参照音声版）→ SQLite書き込み |
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

2種類の生成UIがある:
- **gradio_gen.py**: VoiceDesign版（caption でスタイル指定）
- **gradio_ref.py**: 参照音声版（アップロードした音声で声質指定）

以下の機能は両方に共通する。

### 基本機能

- **generate_forever モード**: ジェネレータ関数で無限ループ生成。Generate Forever / Cancel Forever ボタンで制御。
- **自動再生（Autoplay）**: チェックボックスで ON/OFF 切り替え。Generate Forever 中でもリアルタイムに切り替え可能。
- **直近N件の履歴表示**: `gr.State` で直近5件のファイルパスを保持し、Audio×5で表示
- **候補グリッド削除**: num_candidatesスライダーおよび32候補グリッドを廃止
- **生成完了時にSQLiteへ書き込み**: 生成パラメータ・ファイルパスを記録

### ファイル名規則

```
{YYYYMMDD_HHMMSS}_{seed}.wav
```

### キュー再生

- Autoplay ON 時、生成された音声はキュー再生プレイヤーに積まれる
- 再生中に新しい音声が来ても中断せず、再生完了後に次を再生する
- キュー最大サイズ: 10件（超過時は古いものから破棄）
- プレイヤーは直近の生成結果より上に配置
- キューリストから個別再生・全削除が可能

### 初期音量制御

- すべての `<audio>` 要素の初期音量を **30%** に設定
- Gradio の `gr.Audio` には音量パラメータがないため、カスタム JavaScript で対応
- `MutationObserver` で Gradio が動的に生成・差し替える `<audio>` 要素を検出し、自動で音量を設定
- ユーザーが音量スライダーを操作すると、その値を `window._currentVolume` に記憶
- 以降に生成される新しい `<audio>` 要素には、ユーザーが最後に設定した音量が適用される
- ページをリロードすると 30% にリセットされる

### Live Update（プロンプト変更反映）

- Generate Forever 中にテキストやキャプションの変更を反映するかどうかを選べる機能
- 「Live Update」チェックボックスで ON/OFF を切り替える（デフォルト: OFF）
- **Generate Forever 実行中でもリアルタイムに切り替え可能**（`queue=False` で即時反映）

#### 動作仕様

| Live Update | 動作 |
|---|---|
| OFF（デフォルト） | Generate Forever 開始時のプロンプトが最後まで使われる |
| ON | 次のイテレーションから最新のプロンプトが反映される |

#### 利用シナリオ例

1. Live Update **OFF** のまま Generate Forever を開始
2. 途中でプロンプトを変更（この時点では反映されない）
3. Live Update を **ON** に切り替え → **次のイテレーションから変更が反映される**
4. Live Update を **OFF** に戻す → **その時点のプロンプトで固定される**

#### 対象パラメータ

| UI | 対象 |
|---|---|
| gradio_gen.py（VoiceDesign版） | text, caption |
| gradio_ref.py（参照音声版） | text のみ（uploaded_audio はファイルのため対象外） |

#### 実装方式

Autoplay の仕組みと同じセッション変数パターンを使用:
- `_session_live_update_flags`: Live Update の ON/OFF をセッションごとに管理
- `_session_live_text` / `_session_live_caption`: テキスト/キャプションの最新値をセッションごとに管理
- `text.change()` / `caption.change()` イベントで即座にセッション変数を更新（`queue=False`）
- ジェネレータのループ内で、各イテレーションの冒頭でセッション変数を参照

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
