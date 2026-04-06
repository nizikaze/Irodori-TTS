# myui-v1 実装TODO

## Phase 1: 基盤（DB）

- [ ] `my/data/` ディレクトリを作成
- [ ] `my/db.py` を実装
  - [ ] DBファイル初期化・テーブル作成（`init_db()`）
  - [ ] generation の INSERT（`insert_generation()`）
  - [ ] generation の SELECT（全件・フィルター付き）

## Phase 2: 生成UI（Gradio）

`gradio_app_voicedesign.py` をベースに `my/gradio_gen.py` を新規作成。

- [ ] `my/gradio_gen.py` を新規作成し、本家からユーティリティ関数をインポート
  - `_resolve_checkpoint_path`, `_build_runtime_key`, `_describe_runtime`,
    `_clear_runtime_cache`, `_parse_optional_float`, `_parse_optional_int`,
    `_format_timings`, `_default_*`, `_precision_choices_for_device`,
    `_on_*_device_change`, `FIXED_SECONDS`
  - `build_ui()` と `_run_generation()` は本ファイルで再実装
- [ ] 候補グリッド（32枠）・num_candidatesスライダーを削除
- [ ] ファイル名規則を `{YYYYMMDD_HHMMSS}_{seed}.wav` に変更
- [ ] 直近5件の履歴表示を実装
  - [ ] `gr.State` で直近5件のパスリストを保持
  - [ ] Audio×5 コンポーネントを配置
  - [ ] 生成のたびにリストを先頭追加・5件に切り詰め
- [ ] autoplay ON/OFF トグルをUIに追加
- [ ] autoplay ON 時、最新の1件に `autoplay=True` を設定
- [ ] generate_forever モードを実装
  - [ ] ジェネレータ関数に書き換え
  - [ ] 「Forever」チェックボックスをUIに追加
- [ ] 生成完了時に `insert_generation()` を呼び出してDB書き込み

## Phase 3: 閲覧UI（Streamlit）

`my/streamlit_history.py` を新規作成。

- [ ] `uv add streamlit` で依存追加
- [ ] 基本レイアウト実装（サイドバー: フィルター、メイン: 一覧）
- [ ] 一覧表示（カード形式）
  - [ ] `st.audio` で再生
  - [ ] text / caption / seed / num_steps / checkpoint / 生成日時を表示
- [ ] フィルター・検索
  - [ ] text / caption のキーワード検索
  - [ ] お気に入りのみ表示
- [ ] ソート（新しい順 / レーティング順 / お気に入り順）
- [ ] 編集機能
  - [ ] レーティング（1〜5）
  - [ ] お気に入りトグル
  - [ ] メモ入力

## Phase 4: 将来実装（タグ）

- [ ] タグ機能（生成UI・閲覧UI両方）
  - [ ] タグの付け外しUI
  - [ ] タグでの絞り込み

## Phase 5: 将来実装（カスタムJS必要）

- [ ] キュー再生（再生中に新しいものが追加されても現在の再生を中断せずキューに積む）
  - 注: `gr.Audio` は `ended` イベントを持たないため、カスタムJSが必要
