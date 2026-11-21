# Phase 3〜4 テスト報告

2026-11-21 JST、Linux 開発機で PR #1（`feat/phase3`）のレビュー修正を検証した。

## 結果

| 対象 | 通過 | 失敗 | 実行コマンド |
| --- | ---: | ---: | --- |
| ホスト C++ 通常 | 60 | 0 | `ctest --test-dir <通常ビルド先> --output-on-failure` |
| ホスト C++ ASan / UBSan | 60 | 0 | `UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir <サニタイザービルド先> --output-on-failure` |
| Python 3.11.18 | 132 | 0 | `uv run --locked --all-packages --python 3.11 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.13.5 | 132 | 0 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |

GCC 14.2.0 と CMake 3.31.6 を使用し、通常は `GROKWATCH_SANITIZERS=OFF`、サニタイザー構成は `ON` でビルドした。修正前には、NVS 呼び出し、取消と後処理の競合、停滞中の POST と返信期限、伏字、再生バッファ、タッチ座標欠損、古い取消応答などの回帰テストが失敗することを確認した。

`bash scripts/check_pii.sh` は作業ツリーのインデックスと変更を含む一時コピーの両方で終了コード 0。一時コピーでは `bash scripts/scan_secrets.sh` のステージ済みファイル検査も終了コード 0。

## ファームウェア

ESP-IDF v5.5.4 の `export.sh` を読み込んでから `firmware` で `idf.py build` を実行した。終了コードは 0。ビルド後の `firmware/dependencies.lock` に差分はなかった。

`python scripts/check_firmware_build.py` で、アプリが **1,187,056 バイト / 4,194,304 バイト**（約 28.3%）であることと、生成したパーティション表を確認した。

| 領域 | オフセット | サイズ |
| --- | --- | --- |
| nvs | `0x9000` | `0x6000` |
| phy_init | `0xF000` | `0x1000` |
| factory | `0x10000` | 4 MiB |

生成された `sdkconfig` では `CONFIG_ESP_WIFI_NVS_ENABLED` と `CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE` がともに無効。ファームは `esp_wifi_init` に `nvs_enable=false` を渡し、Wi-Fi 設定を RAM に置く。固定版 M5GFX 0.2.30 のビルド済みライブラリには `nvs_*` への未解決参照がなかった。

## GitHub Actions

コミット `94b8808` の PR #1 で、`ci.yml` の全ジョブ（host-tests 通常・サニタイザ、python 3.11・3.13、`espressif/idf:v5.5.4` コンテナの firmware-build）と `secrets-pii.yml` が成功した。

途中の失敗も記録する。

- `723574b`: firmware-build がコンテナ内の Git 所有者の不一致（dubious ownership）で失敗した。`b9d11cc` で `safe.directory` を設定して解消。
- `a8c9584`: firmware-build がクリーン環境で失敗した。M5GFX の複製を生成時（generate）に書いていたため、ソースの存在検査に間に合わなかった。`94b8808` で設定時（configure）に書くよう直し、追跡ファイルだけを展開した新しい場所でのクリーンビルドも成功した（アプリ 1,187,056 バイト、`dependencies.lock` の差分なし）。

## レビュー

- 1 回目: 64 点（high 1 件: NVS 初期化が書き込みや消去を起こし得る）と 78 点。
- 2 回目: 81 点（high 0 件、mid 5 件）と 86 点（high 0 件）。どちらも合格。

2 回目で残った mid は次のとおり。

- 番号のない遅延通知（`state{idle}`・`error{no_speech}`）が次の収音を止め得る。
- 座標が欠けたとき、補間中の視線が最後の座標へ動き続ける。
- WS イベントキューが満杯になると切断する。
- 圧縮付きの `/v1/reply` で、サイズと署名の対象が展開後の本文になる。
- aiohttp のエラーロガーが接続元を出し得る。

これらは 2026-11-21 の再修正で解消した。実測結果を下に記録する。

## 2 回目レビューの残件修正

回帰テストを修正前に追加し、既存の誤動作で失敗することを確認してから実装した。変更後は各テストが通過した。

| 対象 | 通過 | 失敗 | 結果 |
| --- | ---: | ---: | --- |
| ホスト C++ 通常 | 65 | 0 | 通過 |
| ホスト C++ ASan / UBSan | 65 | 0 | LeakSanitizer を有効にして通過 |
| Python 3.13.5 | 137 | 0 | 通過 |
| Python 3.11.18 | 137 | 0 | 通過 |

ESP-IDF v5.5.4 のクリーンビルドは、追跡ファイルと作業中の非除外ファイルを新しい一時ディレクトリへ展開して実行した。既存の生成設定に合わせて `idf.py set-target esp32s3` を実行してから `idf.py build` を実行し、終了コード 0 を確認した。`scripts/check_firmware_build.py` で、アプリサイズ **1,188,224 バイト / 4,194,304 バイト** とパーティション表を確認した。

`bash scripts/check_pii.sh` は作業ツリーへの変更後に実行し、終了コード 0 だった。実機書き込みと USB 操作は行っていない。

2 回目レビューの mid 5 件を解消した。端末は古い番号の `state` と `error`、および Listening 中の番号なし通知を無視する。座標欠損時の視線は表示値に止まる。WS の音声キュー満杯では音声を数えて捨て、制御イベント用キューを保つ。`/v1/reply` は圧縮本文を 415 で拒否する。aiohttp の HTTP パーサーログは接続元と例外本文を出さない。Claude の low #2 だった `M5.Display.touch()` の null 判定も追加した。

## 未検証

- Phase 5 の C152 実機。ハードウェア版、NVS 無効時の Wi-Fi 初期化と接続、画面・目・タッチ、Idle の撮影と描画性能、収音・VAD、再生・バッファ満杯時の挙動・リング、各状態の見分け、切断・発話中のタッチ、再接続と長時間稼働、消費電力・電池・発熱、工場データとの整合、フルバックアップ・書き込み・復旧。実施条件と確認項目は [仕様 §12](PHASE3_SPEC.md#12-実機でしか確かめられないことphase-5-用) に従う。
- Phase 6 の Mac mini と伝書鳩。whisper.cpp のモデル、日本語認識の精度と処理時間、`say` の日本語音質と 16 kHz 出力、Keychain、LAN とファイアウォール、本物の webhook の起動時間と利用量、Tailscale での返信・署名・再送、返信の制約、既存の記憶と Skills、操作の拒否、会話の待ち時間、任意の `gbot`。
