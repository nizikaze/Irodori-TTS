#!/usr/bin/env bash
# 独自生成UI（Gradio）ネットワーク公開用起動スクリプト
# 同一ネットワーク内の別PCからもアクセス可能にするための設定
#
# 注意:
#   このスクリプトは他のデバイスから本PCにアクセスする用途を想定しています。
#   ローカル環境内での使用を推奨します。

cd "$(dirname "$0")/.."

# MacのIPアドレスを取得（en0: Wi-Fi, en1: Ethernet）
if command -v ipconfig >/dev/null 2>&1; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
else
    LOCAL_IP=$(hostname -I | awk '{print $1}')
fi

echo "======================================"
echo "🌐 ネットワーク公開モードでGradioを起動します"
if [ -n "$LOCAL_IP" ]; then
    echo "▶ 他のPCからのアクセス用URL: http://${LOCAL_IP}:7862"
else
    echo "▶ 他のPCからは、このPCのIPアドレスにポート7862でアクセスしてください"
fi
echo "======================================"

# 外部からのアクセスを許可するため --server-name 0.0.0.0 を指定
uv run python -m my.gradio_gen --server-name 0.0.0.0 --server-port 7862
