#!/usr/bin/env bash
# 閲覧UI（Streamlit）起動スクリプト
# サーバー起動後、ブラウザで自動的に開く
#
# Why ポート8502:
#   デフォルトの8501はStreamlitの既定ポートで他と被りやすいため、
#   8502を使用する

cd "$(dirname "$0")/.."

# Why PYTHONPATH:
#   Streamlitのスクリプトランナーはスクリプトのあるディレクトリ（my/）を
#   sys.pathに追加するが、プロジェクトルートは追加しない。
#   そのため「from my.db import ...」のようなインポートが失敗する。
#   PYTHONPATHにプロジェクトルート（カレントディレクトリ）を設定して解決する。
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

uv run streamlit run my/streamlit_history.py --server.port 8502
