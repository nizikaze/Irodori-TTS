# ネットワーク公開状態でのアクセスガイド

固定IPが設定できない環境や、毎回IPアドレスを調べるのが手間な場合に、他のデバイスから Irodori-TTS（Gradio生成UI / Streamlit履歴UI）へスマートにアクセスするための推奨方法をまとめました。

## 1. Macのローカルホスト名（`.local`）を使用する（一番おすすめ）
IPアドレスの代わりに、Macにつけられたネットワーク名（Bonjour/mDNS）を使ってアクセスする方法です。
設定不要で最も手軽です。

**アクセスURLの例:**
- Gradio生成UIの場合: `http://fukudatadashikinoMac-Studio.local:7862`
- Streamlit履歴UIの場合: `http://fukudatadashikinoMac-Studio.local:8502`

> **💡 さらに使いやすくするコツ**
> Macの「システム設定 > 一般 > 共有」にある「ローカルホスト名」を、短い名前（例: `macstudio` など）に変更すると、`http://macstudio.local:7862/` という非常に短いURLでアクセスできるようになります。

## 2. Tailscale を導入する（外出先からのアクセス・固定IP化）
[Tailscale](https://tailscale.com/) という無料のセキュアなVPNツールを使用する方法です。

Macとアクセスしたい別PCの両方に Tailscale アプリをインストールし、同じアカウントでログインするだけで、**安定して利用できる専用の固定IPアドレス（例: 100.x.x.x）** が割り当てられます。

- **メリット:** 自宅のIPアドレスが変わっても影響を受けません。また、外出先のカフェやスマートフォンの回線からでも、安全に自宅のIrodori-TTSへアクセスできるようになります。

## 3. Webhookを使った自動通知（Discord / Slack）
`my/run_gen_public.command` などの起動スクリプトの末尾に、DiscordやSlackの Webhook URL を叩く `curl` コマンドを追記する方法です。

**実装例（Discordの場合）:**
```bash
LOCAL_IP=$(ipconfig getifaddr en0)
WEBHOOK_URL="https://discord.com/api/webhooks/xxxx/yyyy"

curl -H "Content-Type: application/json" \
     -X POST \
     -d "{\"content\": \"Irodori-TTSが起動しました！ URL: http://${LOCAL_IP}:7862\"}" \
     $WEBHOOK_URL
```

- **メリット:** 起動時に自動でチャンネルへ現在のIPアドレスが通知されるため、IPを調べる必要がなくなり、通知のリンクをクリックするだけでアクセスできるようになります。

## 4. Gradio の Share機能 を使用する
※これはインターネット上に一時的な公開URLを発行する機能です。Gradio起動スクリプトの引数として `--share` を指定する（実装を追加する必要があります）と発行されます。

- **注意点:** 世界中のどこからでもアクセスできる一時URLが生成されますが、誰でもアクセスできてしまうセキュリティリスクがあることや、72時間でリンクが期限切れになるため、恒久的な使用には向きません。
