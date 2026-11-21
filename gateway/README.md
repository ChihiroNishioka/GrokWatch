# ゲートウェイ

ゲートウェイは C152 の WebSocket を認証し、音声認識、ブリッジへの発話送信、応答の音声合成を行います。

## Linux でモックを起動する

リポジトリのルートで実行します。デバイストークンは起動ごとに生成します。

```bash
export GROKWATCH_ALLOW_ENV_SECRETS=1
export GROKWATCH_DEVICE_TOKEN="$(uv run --locked --all-packages python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export GROKWATCH_GATEWAY_HOST=localhost
export GROKWATCH_BRIDGE=mock GROKWATCH_STT=mock GROKWATCH_TTS=mock
uv run --locked --all-packages python -m grokwatch_gateway
```

同じ開発機の別のシェルで `curl -4 --fail http://localhost:8767/healthz` を実行します。起動直後は `status` が `ok`、`bridge.name` が `mock`、`device_connected` が `false` です。試験用クライアントで発話から応答まで確認するには、`uv run --locked --all-packages pytest tests/e2e` を実行します。起動したプロセスは Ctrl+C で停止します。

## 設定

- デバイス接続は `/v1/ws`、既定ポートは `8765` です。モック以外で LAN に接続する場合は `GROKWATCH_GATEWAY_HOST` と `GROKWATCH_GATEWAY_PORT` を設定します。
- `/healthz` と `/v1/reply` は IPv4 ループバックで待ち受けます。ポートを変更するには `GROKWATCH_REPLY_LISTEN` を使います。
- `GROKWATCH_DEVICE_TOKEN` は 32 文字以上が必要です。通常は macOS Keychain のサービス名 `grokwatch`、アカウント名 `GROKWATCH_DEVICE_TOKEN` から読みます。`GROKWATCH_ALLOW_ENV_SECRETS=1` は開発・テスト用です。
- 実音声処理の設定は `GROKWATCH_STT=whisper_cpp`、`GROKWATCH_WHISPER_MODEL`、`GROKWATCH_TTS=macos_say` です。コマンド実体と日本語音声は `GROKWATCH_WHISPER_BIN`、`GROKWATCH_TTS_VOICE` で指定できます。
- 設定は起動時の環境変数から読みます。本文ログは既定で無効です。`GROKWATCH_LOG_TEXT=1` はローカル調査でだけ使います。

ブリッジの切り替えと Mac mini の導入手順は [ブリッジの設定](../bridge/README.md) と [セットアップ](../docs/SETUP.md) を参照してください。`deploy/macos` には設置用ファイルを用意しています。Mac mini への配置と設定変更はオーナーの承認後に行います。
