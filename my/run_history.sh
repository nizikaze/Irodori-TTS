#!/usr/bin/env bash
# 閲覧UI（Streamlit）起動スクリプト
# サーバー起動後、ブラウザで自動的に開く

cd "$(dirname "$0")/.."

uv run streamlit run my/streamlit_history.py --server.port 8501
