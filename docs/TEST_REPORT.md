# Phase 3〜4 テスト報告

2026-11-21 JST、Linux 開発機で Review 6 の修正を検証した。Mac、Mac mini、実機には触れていない。

## 結果

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| ホスト C++ 通常 | 67/67 通過 | `/tmp/gw-fix7-host` で configure、build、ctest |
| ホスト C++ ASan / UBSan | 67/67 通過 | `/tmp/gw-fix7-host-sanitized` で sanitizer 付き configure、build、ctest |
| Python 3.13.5 | 171/171 通過 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.11.18 | 171/171 通過 | 同じ pytest 対象を Python 3.11 で実行 |
| macOS 配置テスト | 25/25 通過 | Keychain、LaunchAgent、dry-run、status の偽コマンド検査 |
| ShellCheck 0.11.0 | 通過 | `deploy/macos/*.sh` を検査 |
| PII 検査 | 通過 | `bash scripts/check_pii.sh` |
| ファームウェア | ビルド不要 | ファームウェアに変更なし |

## Review 6 の確認

- Keychain の偽 `security` で引数、2回の入力、入力不足、無応答、長い出力後の再入力、権限超過、FIFO の非ブロッキング拒否を確認した。期限切れは子を終了し、PTY を閉じて非0で終わる。
- LaunchAgent の再適用、子プロセスのリスナー、停止待ち、bootstrap 失敗、heredoc を使わない dry-run を偽コマンドで確認した。
- Tailscale の `ipn/ipnlocal/serve.go` にある `serveWebHandler` はマウントパスを `StripPrefix` で除く。`reverseProxy.ServeHTTP` は残ったパスを設定済みの転送先パスに結合するため、転送先にも `/v1/reply` を指定する。Gateway の GET は 405、署名付き POST は `200 {"status":"accepted"}` を返す。
- 返信本文は Markdown 記号、URL、絵文字を整え、整形後に空なら 422 で保留要求を受理しない。

## 未検証

- macOS の Keychain、LaunchAgent、受信許可ダイアログと Tailscale Serve の HTTPS 到達性は未確認。C152 実機も未確認。

## 音量機能の検証

2026-11-22 JST、Linux 開発機で音量機能の変更を検証した。StopWatch C152、Mac、Mac mini には触れていない。

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| ホスト C++ 通常 | 93/93 通過 | `cmake -S firmware/host_test -B build/host-vol -DGROKWATCH_SANITIZERS=OFF`、build、ctest |
| ホスト C++ ASan / UBSan | 93/93 通過 | `build/host-vol-san`、`UBSAN_OPTIONS=halt_on_error=1` でctest |
| Python 3.13.5 | 180/180 通過 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.11.18 | 180/180 通過 | 同じ pytest 対象を Python 3.11 で実行 |
| ファームウェア | 通過 | ESP-IDF 5.5.4で `cd firmware && idf.py build`。`scripts/check_firmware_build.py` も通過 |
| factory アプリ領域 | 1,195,056 / 4,194,304 bytes | `check_firmware_build.py` のサイズ検査 |
| 秘密検査 | 通過 | `bash scripts/scan_secrets.sh`、検出なし |
| PII 検査 | 通過 | `bash scripts/check_pii.sh` |

host test は段・利得・デバウンス・長押しの加速・端での停止を検査した。音量0、中間、255のアバター寸法と全描画状態の範囲も検査した。コーデック初期化失敗の後始末は生成した固定版M5Unifiedソースを確認してビルドした。

## 音量機能の実機確認

- ボタン、タッチとの同時操作、電源ボタン、音量の聞こえ方、最大音量の歪み、表示の見え方、録音と再生の切り替えは未確認。
