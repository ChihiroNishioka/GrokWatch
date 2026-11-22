# Gateway の秘密を Keychain に保存する

Gateway は `grokwatch` サービスの一般パスワード項目から秘密を読みます。アカウント名は `gateway/src/grokwatch_gateway/config.py` に対応します。

| アカウント | 必要な条件 |
| --- | --- |
| `GROKWATCH_DEVICE_TOKEN` | 常に必要 |
| `GROKWATCH_WEBHOOK_URL` | `GROKWATCH_BRIDGE=webhook` のとき必要 |
| `GROKWATCH_WEBHOOK_KEY` | `GROKWATCH_BRIDGE=webhook` のとき必要 |
| `GROKWATCH_OPENAI_API_KEY` | `GROKWATCH_BRIDGE=realtime` のとき必要 |
| `GROKWATCH_TASK_WEBHOOK_URL` | 任意（realtime の作業の依頼用。なければ依頼を受けられない） |
| `GROKWATCH_TASK_WEBHOOK_KEY` | 任意（同上） |

realtime の 3 項目は `bash deploy/macos/set-realtime-keys.sh` で案内に沿って登録できます。
## 対話形式で登録する

アカウント名を補助スクリプトに渡します。スクリプトは `security add-generic-password -s grokwatch -a <account> -U -w` を実行します。`-w` に値を渡さないため、`security` が入力を求めます。

```bash
bash deploy/macos/keychain-add.sh GROKWATCH_DEVICE_TOKEN
bash deploy/macos/keychain-add.sh GROKWATCH_WEBHOOK_URL
bash deploy/macos/keychain-add.sh GROKWATCH_WEBHOOK_KEY
```

## 権限を制限したファイルから登録する

入力ファイルの権限を `0600` 以下にします。権限が `0600` より広いファイルは拒否します。補助スクリプトはファイルの内容を非表示の端末入力から送るため、値はプロセス引数やコマンド出力に現れません。`security` が出す値の入力と確認入力の両方に、同じ内容を一度ずつ送ります。15 秒以内に両方の入力を確認できない場合は失敗します。

```bash
chmod 600 "$TMPDIR/gw-secret"
bash deploy/macos/keychain-add.sh --file "$TMPDIR/gw-secret" GROKWATCH_DEVICE_TOKEN
rm -f "$TMPDIR/gw-secret"
```

Webhook 項目を登録するときは、アカウント名を置き換えて実行します。値をリポジトリ、コマンド引数、シェル履歴、ログに書かないでください。

## 項目の有無を確認する

値を表示しないように、`-w` を付けずに実行します。

```bash
security find-generic-password -s grokwatch -a GROKWATCH_DEVICE_TOKEN
```

インストーラーも同じ方法で項目の有無を確認し、不足しているアカウント名だけを表示します。`mock` ブリッジを選んだ場合、Webhook 項目は読みません。

## 項目を手動で削除する

アンインストールでは Keychain 項目を残します。Gateway を停止してから、対象のアカウント名を指定して `security delete-generic-password -s grokwatch -a <account>` を実行してください。
