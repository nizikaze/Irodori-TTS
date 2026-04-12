# macOS 動作メモ

このリポジトリを Mac で動かすときの要点まとめ。

## 結論

コア推論は Mac でも動く。自作部分の Windows 専用スクリプトだけケアすれば CUDA なしでも使える。ただし速度は CUDA 環境と比べると大幅に落ちる。

## Mac でそのまま動く部分

- **本体は macOS (MPS) サポート済み**
  - [README.md:53](../../README.md#L53) に明記
  - [pyproject.toml:36-37](../../pyproject.toml#L36-L37) で cu128 index は `linux` / `win32` のみ対象。macOS は `uv sync` でデフォルト PyTorch が入る
- **推論は MPS で実行可能**
  - `infer.py --model-device mps` が用意されている（[README.md:176](../../README.md#L176)）
- **自作 UI の起動スクリプトは bash 実装済み**
  - [my/run_gen.sh](../run_gen.sh) — Gradio 生成 UI
  - [my/run_history.sh](../run_history.sh) — Streamlit 閲覧 UI

## Mac だと手当が必要な部分

### 1. Windows 専用の .bat ファイル

以下は `netstat` + `taskkill` を使った Windows 専用ユーティリティ。推論ロジックとは無関係で、単にポートを掴んでいるプロセスを殺すだけ。

- [my/kill_any_port.bat](../kill_any_port.bat)
- [my/kill_port_gen.bat](../kill_port_gen.bat)

Mac で使うなら `lsof -ti:<port> | xargs kill -9` 相当の `.sh` を追加する。

### 2. パフォーマンス

- CUDA は使えないので MPS か CPU 実行になる
- Flow Matching のデフォルト 40 ステップ推論だと MPS でもかなり待たされる想定

### 3. ビルド依存の未検証項目

以下は macOS 実機での動作確認をしていないため、インストール時に詰まる可能性あり。

- `torchcodec`
- `dacvae`（git install）

### 4. `.venv/` は Windows 用

リポジトリにコミットされている `.venv/` は Windows 向けなので Mac では使わない。`uv sync` で作り直す。
