# tailnet に返信口だけを公開する

Gateway は `127.0.0.1:8767` で待ち受けます。Tailscale Serve は HTTPS を終端し、`/v1/reply` の要求だけを Gateway に転送します。返信口の URL は `https://<mac-mini>.<tailnet>.ts.net/v1/reply` の形です。

[Tailscale Serve の公式 CLI リファレンス](https://tailscale.com/docs/reference/tailscale-cli/serve)は、HTTPS プロキシとパスのマウントを定義しています。Serve は tailnet 内だけに公開します。Funnel はインターネットへ公開するため、この手順では使いません。

## 既存の Serve 設定を確認する

設定を追加する前に、既存の経路を確認します。無関係な経路がある場合は、所有者と影響を確認するまで続けないでください。

```bash
tailscale serve status --json
tailscale funnel status --json
```

Serve の出力に予期しない経路がないことを確認します。Funnel に有効な公開経路がないことも確認します。

## 返信口の経路を追加する

Gateway を起動し、`status.sh` が正常な待ち受けを報告することを確認してから、経路を追加します。

```bash
tailscale serve --bg --https=443 --set-path=/v1/reply http://127.0.0.1:8767/v1/reply
tailscale serve status --json
```

Serve の出力に `/v1/reply` が Gateway の経路として現れ、予期しない経路がないことを確認します。別の tailnet 端末から GET を送り、HTTP 405 が返ることを確認します。Gateway はこのパスで POST だけを受け付けます。404 が返る場合は、転送先 URL と Gateway の状態を確認します。

```bash
curl --include --max-time 10 https://<mac-mini>.<tailnet>.ts.net/v1/reply
```

署名付き POST は有効な返信要求がある状態で確認します。要求を発生させ、返信を送るコンピューターで、[Webhook 仕様](../../docs/BRIDGE_WEBHOOK.md)の「伝書鳩のルーチン」にある `send_reply` 関数を使います。`base_url` には返信口のベース URL、`request_id` と `reply_token` にはその要求の値を渡します。HTTP 200 と `{"status":"accepted"}` が返れば Gateway が受け付けています。これらの値をリポジトリやシェル履歴に保存しないでください。

`--bg` は Serve の設定をバックグラウンドで保持します。Tailscale が HTTPS 証明書を用意します。

## 返信口の経路を解除する

この手順で追加したマウントだけを解除します。

```bash
tailscale serve --https=443 --set-path=/v1/reply off
tailscale serve status --json
tailscale funnel status --json
```

返信口の経路が消え、Funnel に公開経路がないことを確認します。`tailscale serve reset` はすべての Serve 設定を消すため、使わないでください。
