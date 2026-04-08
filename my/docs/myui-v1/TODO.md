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

## Phase 4: 閲覧修正
- [x] 保存ボタンを押すと保存には成功するが、エラーも出るのを修正

## Phase 5: 生成修正
- [x] Generate foreverやめると生成履歴が全部エラー表示になる

## Phase 6: 閲覧UI修正
- [x] 画面が狭いとseedが横に重なるのを修正
- [x] 作成日時が年月までしかないので日と時分秒まで追加

## Phase 7: キュー再生（カスタムJS）
- [x] キュー再生（再生中に新しいものが追加されても現在の再生を中断せずキューに積む）
  - `gr.Blocks(head=...)` でカスタム JS を注入
  - MutationObserver で `#audio-0` 内の `<audio>` 要素の src 変更を監視
  - 再生中に新しい音声が来たら autoplay 属性を除去しキューに積む
  - `ended` イベントで次のキューアイテムを自動再生
  - キュー最大サイズ: 10件（超過時は古いものから破棄）
  - キューインジケーター（`#queue-indicator`）で待ち件数を表示
  - autoplay OFF 時はキュー再生も無効（従来と同じ動作）

## Phase 8: Generate Foreverに関する挙動をEasyReforgeに寄せる
- [ ] Generate Forever中であることがわかりやすいように、生成ボタンの近くにGenerate Forever中だけ動くアイコンを設置
- [ ] 現在のチェックボックスとストップボタンによるUIから、Generate ForeverボタンとCancel ForeverボタンでGenerate ForeverをコントロールするUIに変更する
- [ ] Generate Forever中にautoplayのチェックを外すと次のファイルからキューに追加しない

## Phase : 


## Phase X: 将来実装（タグ）

- [ ] タグ機能（閲覧UIのみ）
  - [ ] タグの付け外しUI
  - [ ] タグでの絞り込み
- [ ] タグの自動設定

