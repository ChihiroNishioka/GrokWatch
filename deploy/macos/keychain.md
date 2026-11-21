# Store Gateway secrets in Keychain

Gateway reads these generic-password items from the `grokwatch` service. The account names match `gateway/src/grokwatch_gateway/config.py`.

| Account | Required when |
| --- | --- |
| `GROKWATCH_DEVICE_TOKEN` | Always |
| `GROKWATCH_WEBHOOK_URL` | `GROKWATCH_BRIDGE=webhook` |
| `GROKWATCH_WEBHOOK_KEY` | `GROKWATCH_BRIDGE=webhook` |

## Add an item interactively

Pass the account name to the helper. It runs `security add-generic-password -s grokwatch -a <account> -U -w` with `-w` last, so `security` prompts for the value.

```bash
bash deploy/macos/keychain-add.sh GROKWATCH_DEVICE_TOKEN
bash deploy/macos/keychain-add.sh GROKWATCH_WEBHOOK_URL
bash deploy/macos/keychain-add.sh GROKWATCH_WEBHOOK_KEY
```

## Add an item from a protected file

Set the source file so only your account can read it. The helper sends the file contents through a hidden terminal prompt. The value does not appear in the process arguments or command output.

```bash
chmod 600 "$TMPDIR/gw-secret"
bash deploy/macos/keychain-add.sh --file "$TMPDIR/gw-secret" GROKWATCH_DEVICE_TOKEN
rm -f "$TMPDIR/gw-secret"
```

Repeat the command with the account name for each webhook item. Do not put the values in this repository, shell command arguments, shell history, or logs.

## Check that an item exists

Omit `-w` to check the item without printing its value.

```bash
security find-generic-password -s grokwatch -a GROKWATCH_DEVICE_TOKEN
```

The installer checks item presence in the same way. It prints only missing account names. It does not read webhook items when you select the mock bridge.

## Remove an item manually

Uninstall leaves Keychain entries in place. To remove one, run `security delete-generic-password -s grokwatch -a <account>` for that account after you stop the Gateway.
