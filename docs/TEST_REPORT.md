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

## net タスクのスタック overflow 修正

2026-11-22 JST、Linux 開発機で `feat/volume` の作業ツリーを検証した。ビルドと自動テストだけを行い、Mac、Mac mini、実機には触れていない。

### 原因と修正

落ちた ELF では `Network` が `netTask` のローカル変数で、枠は 7,792 B だった。`Network` の `Socket` は 4,096 B のテキストバッファと、`SocketEventQueue` の 768 B 配列を持つ。`diagScan` も 20 個の `wifi_ap_record_t` をローカルに置き、枠は 1,920 B だった。Wi-Fi 診断走査経路は関数枠の合計が 10,160 B で、ログと IDF 用の 3,072 B を足すと 13,232 B になり、net タスクの 12,288 B を超えた。

`Network` と AP 記録配列を静的領域へ移した。`netTask` は 144 B、`diagScan` は 80 B になった。診断ログの書式と音量機能の動作は変えていない。`diagScan` のあとと WebSocket の初回接続時に net タスクの残量を記録する。

| 関数 | 修正前 | 修正後 | 上限 |
| --- | ---: | ---: | ---: |
| `netTask` | 7,792 B | 144 B | 2,048 B |
| `diagScan` | 1,920 B | 80 B | 2,048 B |
| `audioTask` | 2,688 B | 2,688 B | 3,072 B の例外 |

### タスク経路の予算

検査器は関数枠を逆アセンブルから読み、各経路に余裕を足して `app_main.cpp` のタスク枠と比べる。net と audio は 3,072 B、buttons と render は 2,048 B を余裕として確保する。

| タスク | 修正前の最大列挙経路の使用見積もり | 修正後の最大列挙経路の使用見積もり | タスク枠 |
| --- | ---: | ---: | ---: |
| net | 13,232 B（診断走査） | 5,072 B（JSON エスケープ解析） | 12,288 B |
| buttons | 2,192 B | 2,192 B | 3,072 B |
| render | 3,008 B | 3,008 B | 6,144 B |
| audio | 5,952 B | 5,952 B | 6,144 B |

この表は検査器に列挙した主要経路の関数枠合計に余裕を足した見積もりである。間接呼び出しと IDF・ライブラリ内部の全経路は解析していない。余裕はそれらの枠を実測した値ではない。

net の主な経路も予算内になった。診断走査は 13,232 B から 3,744 B、WebSocket の JSON エスケープ解析は 12,720 B から 5,072 B、メッセージ検証は 12,608 B から 4,960 B になった。

### 検証結果

| 対象 | 結果 | 実行内容 |
| --- | --- | --- |
| ホスト C++ 通常 | 94/94 通過 | `GROKWATCH_SANITIZERS=OFF` で configure、build、ctest |
| ホスト C++ ASan / UBSan | 94/94 通過 | `GROKWATCH_SANITIZERS=ON`、`UBSAN_OPTIONS=halt_on_error=1` で ctest |
| Python 3.13.5 | 186/186 通過 | gateway、bridge、e2e、repo の pytest |
| Python 3.11.18 | 186/186 通過 | 同じ pytest 対象 |
| スタック検査 | 旧 ELF は期待どおり失敗。新 ELF は通過 | `scripts/check_stack_frames.py` を旧 ELF と新しいクリーンビルド ELF に実行 |
| ファームウェア | クリーンビルドとパーティション検査が通過 | 追跡ソースと今回の変更を新しい場所へ展開し、`sdkconfig.local.defaults` なしで ESP-IDF 5.5.4 を実行 |
| アプリサイズ | 1,195,280 bytes | factory 領域 4,194,304 bytes 以下 |

実機は未確認である。`diag stack net free=%u` はビルド済みソースにあり、実機での残量はまだ記録していない。
