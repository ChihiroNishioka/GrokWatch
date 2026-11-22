# ブリッジ

ブリッジはゲートウェイから発話を受け取り、選択したアダプタで応答を返します。`GROKWATCH_BRIDGE` を設定してから [ゲートウェイ](../gateway/README.md) を起動します。

| 設定値 | 使い方 |
| --- | --- |
| `mock` | 開発用。`GROKWATCH_MOCK_REPLY` で固定の応答文を指定できます。署名付きの返信経路は `GROKWATCH_MOCK_MODE=post_reply` で試せます。 |
| `webhook` | 既定値。Keychain サービス `grokwatch` に `GROKWATCH_WEBHOOK_URL` と `GROKWATCH_WEBHOOK_KEY` を登録します。値のどちらかが欠けると `/healthz` は `degraded` を返します。受信側の設定は [webhook 仕様](../docs/BRIDGE_WEBHOOK.md) を参照してください。 |
| `gbot_cli` | 任意の非公式アダプタです。利用者が別途入れた `gbot` とアプリのセッションに依存します。`GROKWATCH_GBOT_BIN` に実行ファイルを指定し、`GROKWATCH_GBOT_ARGS` に CLI が受け付ける引数を JSON 配列で設定します。`{agent_id}` は環境変数 `GROKWATCH_AGENT_ID` の値に置き換わります。発話は標準入力、返信は標準出力を使います。 |

外部サービスを呼ばずにブリッジのテストを実行できます。

```bash
uv run --locked --all-packages pytest bridge/tests tests/e2e
```

本物の webhook、返信経路、任意の CLI は Phase 6 で確認します。Mac mini への配置はその確認後です。
