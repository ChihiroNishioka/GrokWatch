# Phase 3〜4 テスト報告

2026-11-21 21:04〜21:10 JST、Linux 開発機。作業主体はエンジニア bot / Codex。ファームウェアのビルド、ホストテスト、モックを使った通信を確認した。

## 結果

| 対象 | 通過 | 失敗 | 実行コマンド |
| --- | ---: | ---: | --- |
| ホスト C++ 通常 | 57 | 0 | `ctest --test-dir build/host-OFF --output-on-failure` |
| ホスト C++ ASan / UBSan | 57 | 0 | `UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/host-ON --output-on-failure` |
| Python 3.11.18 | 119 | 0 | `uv run --locked --all-packages --python 3.11 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.13.5 | 119 | 0 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |

ホストテストは GCC 14.2.0 と CMake 3.31.6 で、`cmake -S firmware/host_test -B build/host-OFF -DGROKWATCH_SANITIZERS=OFF` および `-B build/host-ON -DGROKWATCH_SANITIZERS=ON` で構成し、各ディレクトリを `cmake --build` した。Python の内訳は各版とも gateway 75、bridge 24、E2E 14、リポジトリ検査 6 件。ゲートウェイの CLI をモック設定で起動し、`GET /healthz` が HTTP 200 と所定の JSON を返すことも確認した。

途中の Python 3.13 実行で、healthz のテスト 3 件と本文伏字のテスト 1 件に失敗した。healthz の本文を先に読み取り、伏字テストでは単独で現れる値を既知の秘密としてテスト設定に渡した。リポジトリ検査の初回は形式許可リストに `.py` がなく 1 件失敗し、両検査の許可リストに追加した。最終実行は上表のとおり。

`bash scripts/check_pii.sh`、同スクリプトの `--history-paths`、`bash scripts/scan_secrets.sh` は一時コピーのステージ済みファイルと既存履歴で終了コード 0。gitleaks 8.30.1 の標準ルールとプロジェクトルールを実行した。別の一時リポジトリで、合成した個人情報、資格情報、未許可形式が当てはまる検査に拒否されることを確認した。

## ファームウェア

`source ~/esp/esp-idf-v5.5.4/export.sh && cd firmware && idf.py build` は終了コード 0。一時コピーではローカル defaults がない状態から `idf.py set-target esp32s3 && idf.py build` も終了コード 0。前後で `firmware/dependencies.lock` の差分はなかった。

`python scripts/check_firmware_build.py` で生成済みのパーティション表とアプリサイズを確認した。アプリは **1,195,744 バイト / 4,194,304 バイト**。factory の使用率は約 29% で、生成表に OTA 領域はない。

| 領域 | オフセット | サイズ |
| --- | --- | --- |
| nvs | `0x9000` | `0x6000` |
| phy_init | `0xF000` | `0x1000` |
| factory | `0x10000` | 4 MiB |

固定版は ESP-IDF v5.5.4、M5Unified 0.2.17、M5GFX 0.2.30、esp_websocket_client 1.6.1。Python 側は uv 0.13.9、`uv.lock` の aiohttp 3.14.5、pytest 9.2.0、pytest-asyncio 1.5.0、PyYAML 6.0.4。

## 未検証

- GitHub Actions 上のジョブと `espressif/idf:v5.5.4` コンテナ内の実行。Linux 開発機ではホスト、Python、ESP-IDF の手順を実行した。
- Phase 5 の C152 実機。ハードウェア版と初期化、画面・目・タッチ、Idle の撮影と描画性能、収音・VAD、再生とリング、各状態の見分け、切断・発話中のタッチ、再接続と長時間稼働、消費電力・電池・発熱、工場データとの整合、フルバックアップ・書き込み・復旧。実施条件と確認項目は [仕様 §12](PHASE3_SPEC.md#12-実機でしか確かめられないことphase-5-用) に従う。
- Phase 6 の Mac mini と伝書鳩。whisper.cpp のモデル、日本語認識の精度と処理時間、`say` の日本語音質と 16 kHz 出力、Keychain、LAN とファイアウォール、本物の webhook の起動時間と利用量、Tailscale での返信・署名・再送、返信の制約、既存の記憶と Skills、操作の拒否、会話の待ち時間、任意の `gbot`。
