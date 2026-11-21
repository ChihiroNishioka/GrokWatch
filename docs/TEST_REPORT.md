# Phase 3〜4 テスト報告

2026-11-21 JST、Linux 開発機で 3 回目レビューの残件修正と Mac mini 設置ファイルを確認した。Mac mini と実機には触れていない。

## 結果

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| ホスト C++ 通常 | 67/67 通過 | `cmake -S firmware/host_test -B /tmp/gw-deploy6-host -DGROKWATCH_SANITIZERS=OFF`、build、ctest |
| ホスト C++ ASan / UBSan | 67/67 通過 | `GROKWATCH_SANITIZERS=ON` で build、`UBSAN_OPTIONS=halt_on_error=1` の ctest |
| Python 3.13.5 | 149/149 通過 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.11.18 | 149/149 通過 | 同じ pytest 対象を Python 3.11 で実行。uv の Python 保存先は書き込み可能なキャッシュに指定 |
| ESP-IDF v5.5.4 | 通過 | `export.sh` の環境で `firmware` から `idf.py build`。生成イメージは 0x121f80 バイト |
| Mac 配置リポジトリテスト | 11/11 通過 | plist、shell 構文、固定 launchctl 対象、偽コマンドを使った dry-run・冪等性・ポート・Keychain 不足検査 |
| ShellCheck 0.10.0 | 通過 | `deploy/macos/*.sh` を検査 |
| PII 検査 | 通過 | `bash scripts/check_pii.sh`。読み取り専用の Git 管理領域に書き込まず、一時 index を使って検査 |

## レビュー残件の確認

- `/v1/reply` の aiohttp Application は `auto_decompress=False` を設定済みだった。gzip 本文で 415 になることと展開器が呼ばれないことを確認した。別の境界テストは受信本文 8,192/8,193 バイトを区別し、HMAC テストはそのままの本文と 1 バイト違う本文を区別する。設定を外した比較では展開器が呼ばれ、新しいテストが失敗した。
- 認証前の不正 UTF-8 テキストは修正前に 1007 で閉じることを確認し、未認証時だけ 4003 に写す処理を加えた。回帰テストは 4003 を確認する。
- ファームは core の単一 FIFO に制御イベントと音声記述子を受信順で格納する。保留音声上限を超えた場合は新しい音声だけを捨てて数え、制御イベントは順序どおり処理する。ホストテストは順序、音声溢れ、制御キュー溢れを確認する。再生バッファの破棄方針と合わせ、仕様 §4.5・§5 に二段階の破棄を明記した。
- plist と macOS スクリプトの検査は Linux 上の偽コマンドで実行した。Keychain、LaunchAgent、Tailscale の実環境は未検証。

## 未検証

- Mac mini への設置、Keychain 登録、実際の whisper.cpp・Kyoko 音声、LaunchAgent の起動、Tailscale Serve の HTTPS 到達性。
- C152 実機の画面・タッチ・収音・再生・通信と、設定・バックアップ・書き込み・復旧。
