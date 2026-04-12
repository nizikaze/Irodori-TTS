#!/usr/bin/env bash
# 閲覧UI（Streamlit）ネットワーク公開用起動スクリプト
# 同一ネットワーク内の別PCからもアクセス可能にするための設定
#
# 注意:
#   このスクリプトは他のデバイスから本PCにアクセスする用途を想定しています。
#   ローカル環境内での使用を推奨します。

cd "$(dirname "$0")/.." || { echo "Error: Failed to change directory" >&2; exit 1; }

# MacのIPアドレスを取得（en0: Wi-Fi, en1: Ethernet）
if command -v ipconfig >/dev/null 2>&1; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
    # ipconfigが存在してもgetifaddrが空の場合のフォールバック
    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP=$(hostname -I | awk '{print $1}')
    fi
else
    LOCAL_IP=$(hostname -I | awk '{print $1}')
fi

echo "======================================"
echo "🌐 ネットワーク公開モードでStreamlitを起動します"
if [ -n "$LOCAL_IP" ]; then
    echo "▶ 他のPCからのアクセス用URL: http://${LOCAL_IP}:8502"
else
    echo "▶ 他のPCからは、このPCのIPアドレスにポート8502でアクセスしてください"
fi
echo "======================================"

# 外部からのアクセスを許可する --server.address 0.0.0.0 を指定
uv run streamlit run my/streamlit_history.py --server.port 8502 --server.address 0.0.0.0