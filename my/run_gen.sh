#!/usr/bin/env bash
# 独自生成UI（Gradio）起動スクリプト
# サーバー起動後、ブラウザで自動的に開く

cd "$(dirname "$0")/.."

uv run python -m my.gradio_gen --server-name 0.0.0.0 --server-port 7862 &
SERVER_PID=$!

echo "サーバーの起動を待機中..."
until curl -s http://127.0.0.1:7862/ > /dev/null 2>&1; do
    sleep 1
done

start http://127.0.0.1:7862/

wait $SERVER_PID
