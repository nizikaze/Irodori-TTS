#!/usr/bin/env bash
# 独自生成UI（Gradio）参照音声版 起動スクリプト
# サーバー起動後、ブラウザで自動的に開く

cd "$(dirname "$0")/.."

uv run python -m my.gradio_ref --server-name 0.0.0.0 --server-port 7863

