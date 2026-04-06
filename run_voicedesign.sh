#!/usr/bin/env bash
cd "$(dirname "$0")"

uv run python gradio_app_voicedesign.py --server-name 0.0.0.0 --server-port 7861 &
SERVER_PID=$!

echo "Waiting for server to start..."
until curl -s http://127.0.0.1:7861/ > /dev/null 2>&1; do
    sleep 1
done

start http://127.0.0.1:7861/

wait $SERVER_PID
