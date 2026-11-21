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

2026-11-22 JST、Linux 開発機で音量機能を検証した。検証対象のソースはコミット `125995d` で、StopWatch C152、Mac、Mac mini には触れていない。

今回のテスト・文書修正ではファームコードを変えず、ファームのビルドは再実行していない。下表のクリーンビルドはコミット `125995d` で以前に確認した記録である。

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| ホスト C++ 通常 | 94/94 通過 | `cmake -S firmware/host_test -B /tmp/gw-volume-fix1-host -DGROKWATCH_SANITIZERS=OFF`、`cmake --build /tmp/gw-volume-fix1-host -j2`、`ctest --test-dir /tmp/gw-volume-fix1-host --output-on-failure` |
| ホスト C++ ASan / UBSan | 94/94 通過 | `cmake -S firmware/host_test -B /tmp/gw-volume-fix1-host-san -DGROKWATCH_SANITIZERS=ON`、`cmake --build /tmp/gw-volume-fix1-host-san -j2`、`UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir /tmp/gw-volume-fix1-host-san --output-on-failure` |
| Python 3.13.5 | 180/180 通過 | `uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo` |
| Python 3.11.18 | 180/180 通過 | 同じ pytest 対象を Python 3.11 で実行 |
| ファームウェア | クリーンビルド通過 | `125995d` の追跡ファイルだけを `git archive` で新しい場所へ展開した。`dependencies.lock` の固定版に合う `managed_components` を複製してビルドした。秘密を含むローカル設定を使ったビルドは別に実行した |
| アプリサイズ | 1,195,168 bytes | クリーンビルドで作成したアプリ |
| 実機 `ota_1` | 5,056 KiB（5,177,344 bytes）。上記アプリは収まる | 書き込み前バックアップのパーティション表控えにある `ota_1` サイズと比較した。実機への書き込みは未実施 |
| factory アプリ領域 | 4 MB（4,194,304 bytes） | リポジトリの `firmware/partitions.csv` にある値。実機のパーティションサイズではない |
| 秘密検査 | 通過 | `bash scripts/scan_secrets.sh`、検出なし |
| PII 検査 | 通過 | `bash scripts/check_pii.sh` |

ホストテストは段、利得、デバウンス、長押しの加速、端での停止を検査した。顔・目・リング・点の寸法表を ±0.05 px で照合し、6 状態の境界条件を6つの経過時間で検査した。Speaking と Thinking では、音量値を毎フレーム 0 から 255、255 から 0 へ動かした。

M5Unified の `Speaker.begin()` 失敗処理と `playRaw` 失敗時の `stop()` は、repo テストで生成ソースの内容と呼び出し順を確認した。どちらの失敗経路もホスト上では実行しておらず、実機でも確認していない。

## 音量機能の実機確認

- TTS が聞こえなかった原因が音量か、値130で聞き取れるか、値130が既定値として適切か、値0で音が止まり再生が Idle まで進むかは未確認。値130でも聞こえない場合に調べる PA/G3、I2S、gateway から届く PCM の振幅も未確認。
- 音量値と聞こえ方がほぼ等間隔に変わるか、段1〜4が実質無音でよいかは未確認。
- 値255での歪みと、電池駆動での電圧低下や再起動は未確認。
- 小さい顔が無音を示すか、1段の大きさの変化が見えるか、段差が不自然でないかは未確認。
- Aで上げ、Bで下げる割り当てと、400 msの初回遅延、加速、毎秒20段の上限が使いやすいかは未確認。
- GPIO1とGPIO2が離したときHighになるか、チャタリングが30 msで収まるか、電源ボタンの動作が変わらないかは未確認。
- 小さい顔でのタップ視線、再生開始・終了時のポップ音、タッチとの同時操作は未確認。
- Speaking中の音量変更と録音・再生の切り替えで、音が途切れたり再接続したりしないかは未確認。
- 実機の `ota_1` への書き込みは未実施。書き込み前バックアップと実機パーティション表の再確認も未実施。

## タスクスタック検査と net overflow 修正

2026-11-22 JST、Linux 開発機で変更を検証した。検証対象はこの修正のコミットである。Mac、Mac mini、実機には触れていない。

### 原因と修正

停止を確認した ELF の識別子は `91e60f887` である。前回の解析で測定した経路の関数枠合計は 10,160 B だった。ここにライブラリと ESP_LOG の枠（推定）が加わり、12,288 B を越えたと推定する。10,160 B は測定値であり、ライブラリとログの加算分は実測値ではない。停止記録だけでは実際に通った関数経路を確定できない。

旧版 `1f8a375` のクリーンビルドでは `netTask` の枠が 7,792 B、`diagScan` の枠が 1,920 B だった。`Network` の `Socket` は 4,096 B のテキストバッファと 768 B のキューを持つ。診断走査経路の測定合計 10,160 B に 3,072 B の推定余裕を加えると 13,232 B になる。新しいグラフ検査は旧 ELF で 10,192 B の直接経路と再帰も検出し、非ゼロで終了した。

`Network` と AP 記録配列に続き、`Capture` と `Playback` の PCM 配列も静的領域へ移した。audioTask は 2,688 B から 64 B になった。1つだけ作る audio タスクが両オブジェクトを所有する。タスク枠 6,144 B は変えていない。接続失敗時に `linkAction` が自身を呼ぶ経路も、同じ切断処理へ進む非再帰の分岐に変えた。

### 呼び出しグラフと余裕

検査器は `call0`、`call4`、`call8`、`call12` から直接呼び出しグラフを作り、各 `xTaskCreate` 入口から DFS で最悪経路を出す。`_vfprintf_r` の 800 B は objdump から読み取った実測値である。各タスクからの外部直接呼び出しで測定できた最大枠も示す。外部ライブラリの呼び出し連鎖全体と余裕は推定である。

| タスク | 最悪経路 | 関数枠合計 | 外部直接枠の最大実測 | 余裕と根拠 | 見積もり / タスク枠 |
| --- | --- | ---: | ---: | --- | ---: |
| net | `netTask` → `Network::run` → `pollSocket` → `receiveText` → `linkAction` → `apply` → `send` → `Socket::sendText` → `encode` → `hasFields` → `Message::string` → `find` | 2,576 B | 80 B `esp_websocket_client_init` | 3,072 B。`_vfprintf_r` 800 B と ESP_LOG、Wi-Fi、FreeRTOS の連鎖を含む推定 | 5,648 / 12,288 B |
| audio | `audioTask` → `Playback::pump` → `AudioLevel::frame` → `AudioLevel::value` | 272 B | 80 B `Speaker_Class::_play_raw` | 3,072 B。M5Unified Mic、Speaker、I2S の連鎖を含む推定 | 3,344 / 6,144 B |
| render | `renderTask` → lambda → `FaceAnimator::frame` → `Blink::update` → `Blink::trigger` → `interval` | 1,136 B | 144 B `LGFX_Sprite::push_sprite` | 3,072 B。M5GFX と M5Unified の描画連鎖を含む推定 | 4,208 / 6,144 B |
| buttons | `buttonTask` → `VolumeKeys::sample` | 144 B | 32 B `gpio_get_level` | 2,048 B。GPIO と FreeRTOS の連鎖を含む推定 | 2,192 / 3,072 B |
| touch | `touchTask` → `GestureDetector::sample` → `GestureDetector::update` | 400 B | 64 B `i2c::transactionWriteRead` | 3,072 B。M5Unified、LGFX I2C、FreeRTOS の連鎖を含む推定 | 3,472 / 4,096 B |

### 静的メモリ

`xtensa-esp32s3-elf-size` の `.bss` は 2,211,437 B から 2,223,525 B へ 12,088 B 増えた。`idf.py size` の内部 DRAM 使用量は 201,987 B から 214,187 B へ 12,200 B 増えた。内部 DRAM は合計 341,760 B で、修正後の静的空きは 127,573 B である。5タスクの枠は合計 31,744 B なので、スタックを差し引いても 95,829 B が動的確保前に残る。内部 DRAM の `.bss` は 86,992 B から 99,136 B へ増えた。アプリは 1,195,392 / 4,194,304 bytes である。Wi-Fi 起動後の実ヒープ空きは実機未確認である。

### 検証結果

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| スタック検査 | 旧 ELF は失敗。修正後 ELF は通過 | `.runs/volume/stack-red2.log` と `stack-green2.log` |
| 修正後 ELF | SHA256 prefix `7a2ddd739` | `scripts/check_stack_frames.py` の先頭行 |
| ファームウェア | クリーンビルドとパーティション検査が通過 | 追跡ファイルの作業コピー、ESP-IDF 5.5.4、`sdkconfig.local.defaults` なし |
| ホスト C++ 通常 | 94/94 通過 | `GROKWATCH_SANITIZERS=OFF` の configure、build、ctest |
| ホスト C++ ASan / UBSan | 94/94 通過 | `GROKWATCH_SANITIZERS=ON`、`UBSAN_OPTIONS=halt_on_error=1` で ctest |
| Python 3.13.5 | 190/190 通過 | gateway、bridge、e2e、repo の pytest |
| Python 3.11.18 | 190/190 通過 | gateway、bridge、e2e、repo の pytest |

実機の high-water 値は未確認である。GREEN の実機条件は起動から10分、再接続と1回以上の JSON・音声送受信の後、全タスクで空き 1,024 B 以上、stack overflow と再起動がないこととする。60秒ごとの診断ログで確認する。
