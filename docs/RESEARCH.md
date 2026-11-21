# Phase 2 先行実装調査

調査日 2026-11-21（JST）。調査時の記録と同日に読み取った参照リポジトリのソースに基づく。ハードウェア動作と現行 Grok Bot アプリとの互換性は未検証。

2026-11-21 JST に開発用 Linux 機で groki-bot の `BOARD=stopwatch` を検証目的でビルドした。初回は managed component の `m5stack/m5gfx` が 0.3.0 に解決され、`esp_psram.h` が見つからず失敗した。`main/idf_component.yml` で M5GFX を `==0.2.30` に固定するとビルドに成功し、`stackchan_idf.bin`（約 2.8 MB）が生成された。これは上流のビルド再現であり、GrokWatch のビルドと実機動作は未検証。

## 参照元と再配布条件

| 参照元・コミット | 概要と確認箇所 | ライセンスと再配布条件 |
| --- | --- | --- |
| [groki-bot](https://github.com/JosssphZhou/groki-bot/tree/699a370493e30b196cc7f73f712322cc55c28ec2) `699a370493e30b196cc7f73f712322cc55c28ec2`（2026-10-31） | `sdkconfig.defaults.stopwatch` は C152 向けの Octal PSRAM と 16 MB フラッシュを設定する。`components/board/board.cpp`、`main/demo_loop.cpp`、`main/render_task.cpp` にボード、タッチ追従、描画の実装がある。上流の `docs/build.md` は ESP-IDF 5.5.4 でのビルドと、アバター DSL 用の Node.js 18 以上を記載している。 | ファーム本体は BSL-1.0。元の著作権表記とライセンス全文を保持する。gateway は MIT で別扱いとし、著作権と許諾文を保持する。配布済みファームに含まれる Emotion Ball データは非商用。Mei、hts_engine、Espressif コンポーネントにも個別条件がある。 |
| [grok-command-watch](https://github.com/hueyluox/grok-command-watch/tree/798ad6a528502cffae47398e813887f01d9cf816) `798ad6a528502cffae47398e813887f01d9cf816`（2026-08-20） | PlatformIO / Arduino で動く C152 向けダッシュボード。`platformio.ini` と `src/main.cpp` にボード設定、電源、AMOLED の休止・復帰がある。接続は USB シリアルまたは BLE。 | MIT。再配布時に `LICENSE` と `NOTICE.md`・`NOTICE.en.md` を保持する。C152 対応の一部は MIT の [codex-micro-stopwatch](https://github.com/digitsisyph/codex-micro-stopwatch) 由来で、元の表記も保持する。 |
| [openai-live-esp32 の stackchan](https://github.com/openai/openai-live-esp32/tree/6520b96840493c285ecbb7c72cace3b8116b619d/examples/stackchan) `6520b96840493c285ecbb7c72cace3b8116b619d`（2026-11-18） | CoreS3 搭載の StackChan K151 / K151-R 向け。ESP-IDF 5.5.2 は例の README の記載。端末が API キーを使い WebRTC で OpenAI Live API に接続する。対象コミットのルート README は Live と Realtime のプロトコルを区別している。NVS を保全する初期化と、全フラッシュのバックアップ手順が参考になる。 | Apache-2.0。ライセンス、該当する NOTICE と帰属表示、変更表示を維持する。libpeer は MIT で、Roboto などのフォントも各通知を確認する。 |
| [M5Stack 公式 C152 仕様](https://docs.m5stack.com/en/core/StopWatch)・[M5Burner](https://burner.m5stack.com/device/stopwatch) | 調査時の記録による仕様と配布事例。コミット対象外。調査時の Burner 掲載は 35 件で、Meta Muse Gadget SDK ベースのアニメアバター・プッシュトゥトーク・Muse アプリ連携の事例があった。 | 公式仕様を参照する。M5Unified と M5GFX は MIT で、再配布時は著作権と許諾文を保持する。Burner の素材は再配布許諾が確認できていないため使用しない。 |

C152 の公式仕様をまとめた調査時の記録では、ESP32-S3R8（240 MHz、デュアルコア）、16 MB フラッシュ、8 MB Octal PSRAM、2.4 GHz Wi-Fi。画面は 1.75 インチの 466×466 AMOLED（CO5300、QSPI）、タッチは CST820B（I²C G47/G48、割り込み G13）。音声は ES8311、MEMS マイク、AW8737A と 1 W スピーカーを使用する。電源周りは M5PM1 と M5IOE1、電池は 450 mAh。ハードウェア版は v1.0 と v1.0.1 の記載があり、調査時の記録は BAT/5V IN のシール表記に注意を挙げている。対象実機の版は未確認。素材および依存物ごとの再配布条件は [第三者ライセンス](../THIRD_PARTY_NOTICES.md) に記載する。

## 機能差分

「あり」は対象 clone のソースに実装を確認した項目を指す。「記載あり（未検証）」は文書、公式仕様、配布紹介で確認した項目を指す。「未確認」は対象実装や資料から判断できなかった箇所を指す。

| 機能 | groki-bot | grok-command-watch | openai-live-esp32 stackchan | M5 公式・Burner | GrokWatch で必要なこと |
| --- | --- | --- | --- | --- | --- |
| 丸型 466×466 描画 | あり。C152 プロファイルと描画タスク。 | あり。`include/CommandWatchUi.h` の 466×466 ダッシュボード。 | 対象外。CoreS3 の矩形 UI。 | 記載あり（未検証）。C152 の丸型 AMOLED。 | 円形レイアウトと自作アバターを描画する。 |
| C152 ボード初期化・電源・AMOLED sleep | あり。C152 初期化と M5PM1。AMOLED sleep 専用処理は未確認。 | あり。電源レール制御と休止・復帰。M5GFX 用パッチも収録。 | 対象外。K151 / K151-R。 | 記載あり（未検証）。M5PM1、M5IOE1。 | 初期化、休止、復帰の順序と消費電力を実機で確認する。 |
| タッチ視線追従 | あり。`main/demo_loop.cpp` が C152 の座標を視線目標へ反映する。 | 対象外。ダッシュボード操作。 | 対象外。タッチ画面は会話 UI。 | 未確認。 | 滑らかな追従、円内制限、左右非対称変形を実装する。 |
| タップ・長押し・スワイプ | あり。`main/demo_loop.cpp` がクリック・長押し・フリックを受け、`components/groki_motion/face_input.cpp` に処理がある。 | あり。`src/main.cpp` と `include/TouchGesture.h` にタップ、電源操作用長押し、スワイプ。 | 記載あり（未検証）。画面の開始・停止タップ。長押し・スワイプは未確認。 | 記載あり（未検証）。C152 のタッチと Burner のプッシュトゥトーク事例。 | タップで瞬き、長押しで会話開始、スワイプで短い反応を返す。 |
| アバター状態 Idle / Listening / Thinking / Speaking / Error | あり。`main/conversation_task.cpp` と `main/shared_state.hpp` に会話状態と障害復帰。目標の五つの見た目との一致は未確認。 | 対象外。Grok Build の状態表示。 | あり。`main/Lights.cpp` に会話に沿う LED 表現。五状態の顔は対象外。 | 記載あり（未検証）。Burner にアニメアバター例。 | 五状態と Disconnected を描き分ける。 |
| マイク・スピーカー | あり。`components/board/board.cpp` と会話・音声タスク。 | あり。スピーカーで完了音。マイクによる会話は対象外。 | あり。`main/main.cpp` で音声読み書きを登録。 | 記載あり（未検証）。C152 の ES8311 と MEMS マイク、スピーカー。 | 双方向の日本語音声と、再生に同期する表情を実装する。 |
| ウェイクワード | あり。`gateway/stackchan_mcp/wake_gate.py`。sherpa-onnx を使うゲートウェイ側の「Hi Grok」。 | 対象外。 | 例の README はウェイクワード検出を対象外と明記。 | 未確認。 | ゲートウェイで「Hi Grok」を検出する。 |
| Wi-Fi 再接続 | あり。`main/wifi_sta.cpp` の切断処理と `main/conversation_task.cpp` のセッション再試行。 | 対象外。USB シリアルと BLE。 | あり。例が組み込む `examples/common/StandaloneWifi.cpp` が切断イベントと再接続を扱う。 | 記載あり（未検証）。2.4 GHz Wi-Fi。再接続は未確認。 | Wi-Fi・ゲートウェイ再起動から復旧し Idle に戻す。 |
| デバイス認証 | あり。`gateway/stackchan_mcp/gateway.py` 側のトークン認証。 | LAN ゲートウェイ向け認証は対象外。 | あり。Live API 向けに端末へ API キーを渡す。 | 未確認。 | 端末用トークンを検証し、Bot 認証情報を端末へ置かない。 |
| Gateway | あり。Python、XiaoZhi WebSocket、Opus、音声ヘルスチェック。 | あり。Ghostty と USB / BLE 間のホスト側中継。 | 対象外。端末から OpenAI Live API へ直結。 | 未確認。 | Mac mini 上で音声認識・合成、認証、ヘルスを担当する。 |
| Grok Bot 接続 | あり。native voice と第三者 CLI の二経路。 | 対象外。Ghostty 上の Grok Build CLI が対象。 | 対象外。OpenAI Live API が対象。 | 未確認。 | webhook で伝書鳩を起動し、返信受け口を設ける。 |
| OTA・Web Flasher | あり。`components/config_service/ota.cpp` と `docs/index.html` に実装。 | OTA・Web Flasher は未確認。 | README に USB 書き込みとバックアップの記載あり（未検証）。OTA・Web Flasher は未確認。 | 記載あり（未検証）。M5Burner 配布。 | 初回は承認付きの USB 書き込みと復旧を設計する。 |
| ライセンスの使いやすさ | ファーム BSL-1.0、gateway MIT。データと依存物は別条件。 | MIT と NOTICE。上流の著作権も保持する。 | Apache-2.0 と個別依存物の通知。C152 への転用範囲を評価する。 | M5Unified / M5GFX は MIT。Burner 素材は個別判断。 | 自作部は MIT。採用したファイルと依存物の表示を維持する。 |

## Grok Bot との接続

groki-bot が Grok Bot に話しかける二経路の接続先は、Cursor 側の Grok Bot バックエンド。xAI API は両経路の接続先に含まれない。

- native voice の `gateway/scripts/gbot_voice_session_bridge.mjs` は、Grok Bot アプリのローカル保存ファイル `sand-secrets.json` を読み、アカウント一覧、アクセストークン、マシン ID と macOS Keychain を使ってログイン済みセッションを利用する。Cursor 側の内部 `GrokBotService` RPC（`WatchGrokBotTranscripts` など）をアプリ用クライアントとして呼ぶ。Gateway の README に、内部 API の利用と Grok Bot 0.71.2 での上流検証の記載あり（現行版は未検証）。
- Gemini 音声経由では `gateway/stackchan_mcp/gbot_brain.py` の `ask_grokbot` が `gbot_http_proxy.py` を経由して第三者 CLI の `gbot` を呼ぶ。CLI がアプリのローカルセッションに依存するという調査時の記録の記録がある。CLI 本体のソースは今回の clone の範囲外。
- grok-command-watch は macOS の Ghostty 上で Grok Build CLI のペイン状態を読み、端末に表示する。伝書鳩への会話経路は持たない。

| 候補 | 公開・非公開 | リアルタイム性 | 必要な設定 | リスク・制約 |
| --- | --- | --- | --- | --- |
| webhook ルーチン | Grok Bot の機能説明による。公式文書の URL と実測は未確認。 | 起動単位。数秒〜数十秒の見込みで実測前。 | 対象ルーチン、送信キー、返信受け口、伝書鳩の実行環境と Mac mini 間の Tailscale。 | 起動ごとに利用量を消費する。起動成功と返信受領を個別に扱う。 |
| email トリガー | Grok Bot の機能説明による。公式文書の URL と実測は未確認。 | 非同期で遅い。実測前。 | 対象の受信箱と送受信経路。 | 配送遅延があり、音声会話の待ち時間が長くなる。 |
| iMessage / Linq | 利用者から使えるメッセージチャネル。外部デバイス向け API の公開仕様は未確認。 | メッセージ単位。実測前。 | 既存チャネル、送信経路と返信の対応づけ。Mac mini の Messages 経由は候補。 | 既存の常駐サービスへの干渉と誤配送。 |
| grok-bot-cli | 公開配布の第三者ツール。非公式でセッション依存。 | メッセージ単位。返信時間とストリーム可否は未検証。 | 利用者が CLI を別途導入し、既存アプリと対象エージェントを設定する。 | アプリ更新で互換性を失う可能性と認証情報の取扱い。 |
| groki-bot native voice | 非公開 RPC とアプリのセッション抽出。 | 上流に音声・文字起こしストリームの実装あり。実測前。 | 上流ではログイン済みアプリとローカルの認証情報に依存する。 | 内部仕様の変更、セッション漏えい。GrokWatch では採用しない。 |

調査した範囲では、公式の外部デバイス向けリアルタイム音声 API を確認できていない。

## 採用方針案

- ESP-IDF 5.5 と MIT の M5Unified / M5GFX を使い、C152 ファームは自作を基本とする。C152 初期化と電源は両 StopWatch 実装、XiaoZhi WebSocket とゲートウェイ構成は groki-bot を参照する。コードを取り込む場合は該当ファイルに元の著作権とライセンス表示を保持し、必要な全文と通知を同梱する。
- Emotion Ball データと groki-bot の顔データを使わず、動画の観察を基に自作する白円と黒いカプセル目を MIT で公開する。
- 既定の接続は webhook とする。任意の `gbot_cli` は利用者が導入する外部ツールを呼ぶ。GrokWatch は CLI を同梱しない。テスト用に `mock` を設ける。native voice の内部 RPC とセッション抽出は実装しない。

## オーナーの確認が必要なこと

- GitHub の公開先アカウント、新規 Public リポジトリ名 `GrokWatch`、初回公開のファイル一覧。GitHub 公開 API の未認証照会は 404 で、同名の非公開リポジトリはログイン環境で確認する必要がある。
- webhook の利用と返信用 Tailscale の設定、および試験時の起動回数の扱い。
- 非公式の `gbot_cli` を任意機能として実装するか。
- 長押しの会話停止への割り当てと、スワイプのモード切替の要否。
- Phase 3 のコード取り込み候補と、Phase 5 の対象機種・バックアップ・書き込みの承認。
