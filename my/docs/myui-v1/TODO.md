# myui-v1 実装TODO

## Phase 1: 基盤（DB）

- [x] `my/data/` ディレクトリを作成
- [x] `my/db.py` を実装
  - [x] DBファイル初期化・テーブル作成（`init_db()`）
  - [x] generation の INSERT（`insert_generation()`）
  - [x] generation の SELECT（全件・フィルター付き）

## Phase 2: 生成UI（Gradio）

`gradio_app_voicedesign.py` をベースに `my/gradio_gen.py` を新規作成。

- [x] `my/gradio_gen.py` を新規作成し、本家からユーティリティ関数をインポート
  - `_resolve_checkpoint_path`, `_build_runtime_key`, `_describe_runtime`,
    `_clear_runtime_cache`, `_parse_optional_float`, `_parse_optional_int`,
    `_format_timings`, `_default_*`, `_precision_choices_for_device`,
    `_on_*_device_change`, `FIXED_SECONDS`
  - `build_ui()` と `_run_generation()` は本ファイルで再実装
- [x] 候補グリッド（32枠）・num_candidatesスライダーを削除
- [x] ファイル名規則を `{YYYYMMDD_HHMMSS}_{seed}.wav` に変更
- [x] 直近5件の履歴表示を実装
  - [x] `gr.State` で直近5件のパスリストを保持
  - [x] Audio×5 コンポーネントを配置
  - [x] 生成のたびにリストを先頭追加・5件に切り詰め
- [x] autoplay ON/OFF トグルをUIに追加
- [x] autoplay ON 時、最新の1件に `autoplay=True` を設定
- [x] generate_forever モードを実装
  - [x] ジェネレータ関数に書き換え
  - [x] 「Forever」チェックボックスをUIに追加
- [x] 生成完了時に `insert_generation()` を呼び出してDB書き込み

## Phase 3: 閲覧UI（Streamlit）

`my/streamlit_history.py` を新規作成。

- [x] `uv add streamlit` で依存追加
- [x] 基本レイアウト実装（サイドバー: フィルター、メイン: 一覧）
- [x] 一覧表示（カード形式）
  - [x] `st.audio` で再生
  - [x] text / caption / seed / num_steps / checkpoint / 生成日時を表示
- [x] フィルター・検索
  - [x] text / caption のキーワード検索
  - [x] お気に入りのみ表示
- [x] ソート（新しい順 / レーティング順 / お気に入り順）
- [x] 編集機能
  - [x] レーティング（1〜5）
  - [x] お気に入りトグル
  - [x] メモ入力

## Phase 4: 将来実装（タグ）

- [ ] タグ機能（閲覧UIのみ）
  - [ ] タグの付け外しUI
  - [ ] タグでの絞り込み

## Phase 5: 将来実装（カスタムJS必要）

- [ ] キュー再生（再生中に新しいものが追加されても現在の再生を中断せずキューに積む）
  - 注: `gr.Audio` は `ended` イベントを持たないため、カスタムJSが必要
