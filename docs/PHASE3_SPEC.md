# Phase 3〜4 仕様と GREEN 一覧

状態は実装済み（ビルドとモックで確認、実機未検証）。しきい値と待ち時間は Phase 5 の実機確認で見直す。

Phase 3 でファームウェア、gateway、bridge を実装し、Phase 4 で開発用 Linux 機のビルドと自動テストで受け入れる。実機（StopWatch C152）、Mac、Mac mini には触れない。受け入れは「11. GREEN when」の全項目が CI で通ること。

関連: [アーキテクチャ](ARCHITECTURE.md)、[webhook ブリッジ仕様](BRIDGE_WEBHOOK.md)、[アバター仕様](AVATAR_SPEC.md)、[参照動画の観察](AVATAR_REFERENCE.md)、[調査](RESEARCH.md)、[分かっている落とし穴](../LESSONS.md)。

## 1. オーナー決定（この仕様の前提）

| 項目 | 決定 |
| --- | --- |
| 長押し | 会話の開始と停止。Idle で開始、Listening で送信、Thinking / Speaking で取り消し。 |
| スワイプ | モード切替なし。ドラッグとして扱う（視線が指に追従するだけ）。 |
| 伝書鳩への経路 | webhook ルーチンが既定。`gbot_cli`（grok-bot-cli）は利用者が自分で入れる任意の非公式アダプタ。groki-bot の内部 RPC・ネイティブ音声は使わない。 |
| 確認の範囲 | 開発用 Linux 機でのビルドとモックだけ。実機での確認は Phase 5 以降。 |

## 2. 範囲と範囲外

### 範囲（Phase 3〜4）

- ファームウェア: ESP-IDF 5.5（v5.5.4）と M5Unified / M5GFX（`m5stack/m5gfx` は `==0.2.30` 固定）で C152 向けにビルドできるプロジェクト。ハード非依存のロジックは `grokwatch_core`（C++17、ESP-IDF 非依存）に置き、ホストテストで確かめる。
- gateway: Python 3.11+ / uv。WebSocket サーバ、STT（mock・whisper.cpp）、TTS（mock・macOS `say`）、`/v1/reply`（HMAC 検証・`request_id` 状態管理）、`/healthz`、構造化ログ。
- bridge: 共通契約 `send_utterance` / `health` / `cancel` と、アダプタ `webhook`・`gbot_cli`・`mock`。
- モック通し試験（偽デバイス → gateway → mock STT → mock bridge → `/v1/reply` → mock TTS → 偽デバイス）。
- CI: 既存の秘密検査に、ホストテスト、pytest、`espressif/idf:v5.5.4` コンテナでのファームビルドを加える。

### 範囲外

| 項目 | 理由・扱い |
| --- | --- |
| 「Hi Grok」ウェイクワード | 長押しで代替。gateway の構成は将来追加できる形にするが、実装しない。 |
| OTA・Web Flasher | 初回は承認付きの USB 書き込み（Phase 5）。OTA 用パーティションも作らない。 |
| Mac mini への配置 | LaunchAgent、Keychain への実値登録、`tailscale serve`、ファイアウォール設定は Phase 6（Mac mini の操作は別途指示）。 |
| 実機への書き込み（Flash）・消去・バックアップ | Phase 5。承認が要る。 |
| 本物の webhook ルーチン・本物の `gbot` の呼び出し | テストは外部ネットワークに出ない。実呼び出しは Phase 5。 |
| `emotion` による表情の変化、会話の自動継続 | v1 では `emotion` をログだけに使い、返事のあとは常に Idle に戻る。 |
| BLE、wss（TLS）、複数台の同時利用 | v1 は LAN 内の平文 `ws://` と 1 台。リスクは「13. 未決とリスク」。 |
| Emotion Ball・groki-bot の顔データ | 取り込まない（[LESSONS](../LESSONS.md)）。 |

## 3. モジュール構成

```
GrokWatch/
├── pyproject.toml              # uv ワークスペース（members: gateway, bridge）。uv.lock をコミット
├── firmware/
│   ├── CMakeLists.txt          # ESP-IDF プロジェクト。PROJECT_VER = 0.1.0
│   ├── dependencies.lock      # ESP-IDF コンポーネントの固定版
│   ├── sdkconfig.defaults      # 秘密を含まない既定値（C152: Octal PSRAM、16 MB フラッシュ）
│   ├── partitions.csv          # nvs / phy_init / factory（OTA なし）
│   ├── main/
│   │   ├── idf_component.yml   # m5stack/m5unified、m5stack/m5gfx ==0.2.30、espressif/esp_websocket_client
│   │   ├── Kconfig.projbuild   # GROKWATCH_* の設定項目（既定は空）
│   │   ├── app.hpp             # タスク間の共有状態
│   │   ├── app_main.cpp        # 初期化とタスク起動
│   │   ├── board.cpp           # M5Unified による画面・タッチ・音声の初期化
│   │   ├── render_task.cpp     # core の FaceModel を M5GFX スプライトに描く
│   │   ├── touch_task.cpp      # 生のタッチ点を core のジェスチャー判定へ渡す
│   │   ├── audio_task.cpp      # 収音 20 ms フレーム化・再生バッファ
│   │   ├── net_task.cpp        # Wi-Fi・WebSocket・再接続
│   │   └── config_store.cpp / config_store.hpp # Kconfig から設定を読む
│   ├── components/grokwatch_core/   # C++17、ESP-IDF・第三者ヘッダ非依存
│   │   ├── CMakeLists.txt      # ESP_PLATFORM なら idf_component_register、そうでなければ add_library
│   │   ├── include/grokwatch/
│   │   │   ├── avatar_state.hpp     # 状態機械
│   │   │   ├── gesture.hpp          # tap / drag / long press
│   │   │   ├── gaze.hpp             # 視線と目の変形
│   │   │   ├── blink.hpp            # 瞬きスケジューラ
│   │   │   ├── drift.hpp            # Idle の漂い・Thinking の左右移動
│   │   │   ├── face_model.hpp       # 1 フレーム分の描画パラメータ
│   │   │   ├── backoff.hpp          # 再接続バックオフ
│   │   │   ├── link_supervisor.hpp  # Wi-Fi・WS・認証の接続状態
│   │   │   ├── protocol.hpp         # v1 メッセージのエンコード / デコード（最小 JSON）
│   │   │   ├── audio_level.hpp      # 振幅レベルと簡易 VAD
│   │   │   ├── config.hpp           # 設定と接続の前提条件
│   │   │   └── rng.hpp / clock.hpp  # 乱数・時刻は注入（テストで固定）
│   │   └── src/*.cpp
│   └── host_test/
│       ├── CMakeLists.txt      # 開発機用。ctest に登録
│       ├── gw_test.hpp         # 自作の最小テストマクロ（TEST / CHECK / CHECK_EQ / CHECK_NEAR）
│       ├── check_core_includes.cmake  # core の #include を検査
│       └── test_*.cpp
├── gateway/
│   ├── pyproject.toml          # grokwatch-gateway。依存は aiohttp。dev: pytest、pytest-asyncio
│   ├── src/grokwatch_gateway/
│   │   ├── __main__.py         # 起動と /healthz
│   │   ├── config.py           # 環境変数と秘密の取得（Keychain / 開発用 env）
│   │   ├── ws_server.py        # デバイス WebSocket（認証・セッション・音声）
│   │   ├── protocol.py         # v1 メッセージの型と検証
│   │   ├── conversation.py     # 1 回の発話の流れ（STT → bridge → TTS）
│   │   ├── reply_server.py     # /v1/reply
│   │   ├── registry.py         # request_id の状態（pending / answered / expired / cancelled）
│   │   ├── audio.py            # STT・TTS のモックと外部コマンド
│   │   ├── canned.py           # 定型音声の文と事前合成
│   │   └── logging.py          # JSON ログと伏せ字
│   └── tests/                  # test_ws.py、test_conversation.py、test_reply.py、test_providers.py、test_logging.py
├── bridge/
│   ├── pyproject.toml          # grokwatch-bridge。gateway に依存しない
│   ├── src/grokwatch_bridge/
│   │   ├── contract.py         # Bridge プロトコル、ReplyChunk、ReplyInbox、例外
│   │   ├── factory.py          # GROKWATCH_BRIDGE で選ぶ
│   │   ├── webhook.py
│   │   ├── gbot_cli.py
│   │   ├── mock.py
│   │   └── signing.py          # HMAC 署名（返信側の参考実装と同じ手順）
│   └── tests/test_adapters.py
├── tests/
│   ├── e2e/                    # モック通し。fake_device.py を含む
│   ├── fixtures/               # 偽の whisper-cli・say・security・gbot（シェルスクリプト）。PCM はテストで生成
│   └── repo/                   # リポジトリの衛生検査
└── .github/workflows/
    ├── secrets-pii.yml         # 既存
    └── ci.yml                  # 新規: host-tests / python / firmware-build
```

依存の向き: `firmware/main` → `grokwatch_core`。`gateway` → `bridge`（契約のみ）。`bridge` は `ReplyInbox` プロトコルを定義し、gateway の `registry` がそれを実装する。bridge は gateway を import しない。

ファームの描画はcore が `FaceModel`（目 2 つの中心・幅・高さ・角丸、リングの種類・半径・太さ・色・点線の位相）を計算し、`render_task` が描画する。ホストテストは `FaceModel` の値を照合し、実際の表示は Phase 5 で確認する。

## 4. 決めた値

### 4.1 画面とアバター

座標は画面左上を原点とするピクセル。`c = (233, 233)`。

| 項目 | 値 |
| --- | --- |
| 画面 | 466×466、RGB565、PSRAM 上のスプライトに描いて一括転送 |
| 背景 / 白円 | 黒 `#000000` / 白 `#FFFFFF`、白円の半径 `R_face = 200` |
| 目 | 黒のカプセル（縦長の角丸長方形、角丸半径 = 幅/2）。基準幅 `w0 = 44`、基準高さ `h0 = 96` |
| 目の中心 | 視線ゼロで `c ± (70, 0)`。左目 `s = -1`、右目 `s = +1` |
| 視線の移動量 | 両目を `g × 50` px 平行移動（`g` は単位円内） |
| 目の安全域 | 目の外接矩形のどの角も `c` から 196 px 以内（白円の 4 px 内側） |
| 目標描画レート | 30 fps（実測は Phase 5） |

### 4.2 視線と目の変形

| 項目 | 値 |
| --- | --- |
| 正規化 | `u = (p - c) / r`、`r = 200`。`g = u / max(1, \|u\|)`。`p == c` のとき `g = (0, 0)` |
| 入力の扱い | 画面外の整数座標（負の値、466 以上）も受け、視線の長さを 1 以下に収める。整数の座標を取得できない場合は直前の視線を保つ |
| 非対称変形 | `d = s × g_x`、`幅 = w0 × (1 - a × d)`、`高さ = h0 × (1 + b × d)`、`a = 0.25`、`b = 0.15` |
| ドラッグ中の平滑化 | 指数平滑、時定数 80 ms |
| 指を離したあと | 300 ms かけて状態ごとの視線（Idle は漂い、Thinking は左右、他は中央）へ戻る |
| タップ時 | 視線をタップ位置へ 120 ms で向け、1.5 秒保持してから状態ごとの視線へ戻る |

### 4.3 瞬き・漂い・状態表現

| 項目 | 値 |
| --- | --- |
| 自発瞬き | Idle と Disconnected。間隔は一様乱数 2,000〜6,000 ms |
| 瞬きの形 | 合計 150 ms（閉じる 60 / 閉じたまま 30 / 開く 60）。最も閉じたとき高さ × 0.08 |
| タップの瞬き | 全状態で即座に 1 回。瞬き中のタップは延長しない（二重瞬きにしない）。タップ後、次の自発瞬きまでの間隔を引き直す |
| Idle の漂い | 1,500〜4,000 ms ごとに半径 0.35 以内の新しい目標点を選び、ease-in-out で移動。タッチの影響がない間は、どの 5 秒間にも窓の先頭からユークリッド距離で 0.02 以上動く |
| Listening | 目の高さ × 1.15。白円の外周に白いリング（半径 214、太さ 4）を常時表示 |
| Thinking | 視線 `g_x = 0.5 × sin(2π t / 2.4 s)`、`g_y = 0`。リングなし。20 秒経過で「まだ考え中」の合図（白円の下に 3 点、600 ms 周期で順に点灯）を足す |
| Speaking | リング（半径 214）の太さを `2 + 8 × level` px（`level` は 0〜1）。再生フレームが 100 ms 途切れたら `level` は 200 ms で 0 まで減衰 |
| 振幅レベル | 20 ms フレームの RMS を `level = clamp(RMS / 6000, 0, 1)` に変換。指数平滑の時定数は立ち上がり 30 ms、減衰 120 ms |
| Error | 琥珀色 `#FFB000` の実線リング（半径 214、太さ 6）。最低 1,500 ms 表示 |
| Disconnected | 灰色 `#808080` の点線リング（半径 214、太さ 4、12 分割）。1 秒周期で明滅（0.5 秒点灯 / 0.5 秒消灯）。目は Idle と同じく漂い・瞬きを続ける |

### 4.4 ジェスチャー

| 項目 | 値 |
| --- | --- |
| 移動のしきい値 | 押した点から 12 px |
| tap | 押してから 300 ms 未満で離し、移動 12 px 以内 |
| long press | 押したまま 600 ms 経過、移動 12 px 以内。指を離す前の 600 ms 到達時点で 1 回だけ発火し、そのあと離してもタップにしない |
| drag | 移動が 12 px を超えた時点から。以後は長押しにならない |
| swipe | 速度・方向を問わず drag として扱う。モード切替なし |
| 長押しの間隔 | 長押し発火後 800 ms 以内の次の長押しは無視（連打による開始→即停止を防ぐ） |
| タッチ点の取得 | 100 Hz（10 ms）でポーリング。読み取り失敗と接触中の生座標 (0, 0) は欠損として扱い、ドラッグ中は最後に取得した座標を保持する |

### 4.5 音声と会話のタイミング

| 項目 | 値 |
| --- | --- |
| 形式 | PCM16LE、モノラル、16,000 Hz、1 フレーム 20 ms = 320 サンプル = 640 バイト |
| 収音の最大長 | 15 秒（750 フレーム）。端末と gateway の両方で打ち切る |
| 端末の簡易 VAD | RMS 500 以上を発話とみなす。発話後、連続 60 フレーム（1,200 ms）の無音で `listen_stop`。開始から 5,000 ms 発話がなければ `listen_stop` |
| gateway の最短発話 | 300 ms（15 フレーム）未満は空の発話として扱う |
| TTS の送出 | `tts_start` のあと、最初の最大 10 フレーム（200 ms 分）を待機なしで送り、11 フレーム目以降は送出開始から 20 ms 刻みの締切に合わせる。最後のフレームはゼロで 640 バイトに埋める |
| ファームの WS 受信キュー | 1 本の順序付きキューに制御イベントと音声フレームを受信順で格納する。保留中の音声は最大 32 フレーム。音声が満杯なら新しい音声を捨てて数える。制御イベントを格納できない場合は接続を復旧する |
| 端末の再生バッファ | 300 ms ためてから再生開始。300 ms 未満で `tts_end` が来たら残りを再生し、空なら完了する。96 フレームで満杯になったら最古のフレームを捨て、破棄数を数えながら接続を維持する |
| 返事待ちの上限 | 90 秒（`GROKWATCH_REPLY_TIMEOUT_S`）。端末側の安全上限は 100 秒（Thinking に入ってから 100 秒で Error → Idle。ping / pong や Thinking の再通知は計時に影響しない） |
| Thinking の合図 | 20 秒（BRIDGE_WEBHOOK.md §5） |

音声の破棄は受信後の 2 段階で扱う。WS 受信キューが満杯なら新しい音声フレームを捨て、破棄数を記録する。受信キューから再生バッファへ移した後、再生バッファが満杯なら最古のフレームを捨て、破棄数を記録する。どちらの音声破棄でも接続を維持し、制御イベントの順序は保つ。

### 4.6 接続と再接続

| 項目 | 値 |
| --- | --- |
| バックオフ | 1 → 2 → 4 → 8 → 16 → 30 → 30 … 秒。各値に ±20% の一様ジッター、ただし 30 秒を超えない・0.8 秒を下回らない |
| リセット | `hello_ok` を受けたら 1 秒からやり直す |
| `auth_error` のとき | Disconnected 表示のまま 30 秒間隔で再試行（短い間隔で叩かない） |
| ping | 端末が 10 秒ごとに `ping`。25 秒間何も受信しなければ切断とみなす |
| gateway の無通信切断 | 30 秒間何も受信しなければ閉じる |
| hello の期限 | 接続から 5 秒以内に `hello` が来なければ gateway が閉じる |
| 切断時 | 端末は収音停止・再生バッファ破棄・Disconnected。gateway は進行中の処理を止め、`pending` があれば `cancelled` にする。復旧後は再認証して Idle |
| 同時接続 | 会話を処理する端末は 1 台。新しく認証できた接続が来たら古い接続を 4004 で閉じる |
| WS 接続枠 | 認証待ちを含め既定 4 接続。`GROKWATCH_WS_CONNECTION_LIMIT` で変更でき、満杯ならアップグレード前に HTTP 503 を返す |

### 4.7 プロトコル v1

| 項目 | 値 |
| --- | --- |
| URL | `ws://<gateway-host>:8765/v1/ws`（ホストとポートは設定から。8765 は既定値） |
| テキストフレーム | UTF-8 の JSON オブジェクト 1 つ、4,096 バイト以下。全メッセージに `"type"` |
| aiohttp の受信上限 | `max_msg_size = 4,160` バイト（4,096 + 64 バイト）。圧縮は無効。パーサーがサイズで拒否したら 4003 で閉じ、認証済みなら先に `error{bad_message}` を送る |
| バイナリフレーム | 音声 1 フレーム（ちょうど 640 バイト）。順序番号は持たない（TCP の順序に任せる） |
| JSON の範囲 | 端末の core は平たいオブジェクト（文字列・整数・真偽値）だけを扱う最小実装。文字列は JSON のエスケープを扱う。入れ子・配列・浮動小数点は不正として扱う |
| 未知の `type`（認証後） | 無視し、診断コードだけをログに残す |
| 認証前の `hello` 以外 | 応答せずに 4003 で閉じる（バイナリ、不正 JSON、不正 UTF-8 テキストも同じ） |
| デバイストークン | 32 文字以上。gateway は `hmac.compare_digest` で比較 |

### 4.8 gateway・bridge

| 項目 | 値 |
| --- | --- |
| デバイス WS の待ち受け | `GROKWATCH_GATEWAY_HOST`（既定 `0.0.0.0`）: `GROKWATCH_GATEWAY_PORT`（既定 `8765`） |
| 返信口と `/healthz` | `GROKWATCH_REPLY_LISTEN`（既定 `127.0.0.1:8767`）。ホストは `127.0.0.1` のみ、ポートは変更可 |
| HTTP / WS ライブラリ | aiohttp（サーバ・クライアントとも）。版は `uv.lock` で固定 |
| webhook 送信 | HTTPS のみ。開発用フラグでループバック IP の HTTP を許可する。リダイレクトは追わない。8 秒、1 回だけ。body 4 KB 以下（`text` は 1,000 文字で切り、UTF-8 で直列化した body が 4,096 バイトに収まるまでさらに切る）。`lang` は `ja-JP`、`max_chars` は 120 |
| `reply_token` | `secrets.token_urlsafe(32)`（32 バイト） |
| `request_id` | UUIDv4 |
| `session_id` / `turn` | `s-<YYYYMMDD>-<3 桁連番>`。長押しで開始するたびに新しい session、v1 の `turn` は常に 1 |
| 返信の検証 | body は最大 8,192 バイト、タイムスタンプは ±120 秒、`text` は最大 400 文字（[webhook ブリッジ仕様 §3](BRIDGE_WEBHOOK.md)） |
| 終了済み記録の保持 | `answered` / `expired` / `cancelled` は 10 分保持して削除（以後は 404） |
| whisper.cpp | `GROKWATCH_WHISPER_BIN`（既定 `whisper-cli`）、`GROKWATCH_WHISPER_MODEL`（必須）。WAV を一時ファイルに書き `-l ja -nt -otxt` で実行。タイムアウト 30 秒 |
| macOS `say` | `GROKWATCH_TTS_VOICE`（既定 `Kyoko`）。本文は一時ファイルから `-f` で渡す（引数に本文を置かない）。`--file-format=WAVE --data-format=LEI16@16000` で直接 16 kHz PCM を得る。タイムアウト 30 秒 |
| `gbot_cli` | `GROKWATCH_GBOT_BIN`（既定 `gbot`、`shutil.which` で探す）、`GROKWATCH_GBOT_ARGS`（JSON 配列、`{agent_id}` は環境変数 `GROKWATCH_AGENT_ID` の値で置換）。本文は標準入力、返事は標準出力。タイムアウト 60 秒 |
| 秘密の取得 | 既定は macOS Keychain（`security find-generic-password -s grokwatch -a <名前> -w`）。開発とテストに限り `GROKWATCH_ALLOW_ENV_SECRETS=1` のとき環境変数から読む |
| 起動時の検証 | デバイストークンが空または 32 文字未満、または返信口のホストが `127.0.0.1` 以外なら起動しない。`webhook` で URL かキーが取れなければ起動はするが `/healthz` で bridge を `unavailable` と返す |

### 4.9 定型音声

| 場面 | error.code | 文 |
| --- | --- | --- |
| webhook の送信失敗 | `bridge_unavailable` | いま伝書鳩につながらないみたい |
| 返事が上限内に来ない | `bridge_timeout` | ごめん、返事が来なかったみたい |
| STT の失敗 | `stt_failed` | うまく聞き取れなかったみたい |
| `status: error` で `text` が空 | `reply_error` | ごめん、いまは答えられないみたい |

定型音声は gateway 起動時に TTS で合成してキャッシュする。TTS も失敗する場合は音声なしで Error → Idle。

### 4.10 端末の設定

| 項目 | Kconfig |
| --- | --- |
| Wi-Fi SSID | `CONFIG_GROKWATCH_WIFI_SSID` |
| Wi-Fi パスワード | `CONFIG_GROKWATCH_WIFI_PASSWORD` |
| gateway ホスト | `CONFIG_GROKWATCH_GATEWAY_HOST` |
| gateway ポート | `CONFIG_GROKWATCH_GATEWAY_PORT`（既定 8765） |
| デバイストークン | `CONFIG_GROKWATCH_DEVICE_TOKEN` |

- 端末設定は Kconfig で渡す。ローカルの値は Git 管理外の `firmware/sdkconfig.local.defaults` に置く。ポート以外の既定値は空。必須値が欠けている場合は「設定なし」と記録し、Disconnected のまま待つ。
- ファームは NVS を使わない。読み取りも書き込みも行わない。M5GFX 0.2.30 のボード検出キャッシュはビルド時に除き、M5Unified の IMU 初期化は無効にする。
- Wi-Fi の `CONFIG_ESP_WIFI_NVS_ENABLED=n` と PHY の `CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE=n` を指定する。`esp_wifi_init` に `nvs_enable=false` を渡し、Wi-Fi 設定は `WIFI_STORAGE_RAM` に置く。

### 4.11 ビルドと CI

| 項目 | 値 |
| --- | --- |
| ESP-IDF | v5.5.4、ターゲット `esp32s3` |
| 依存の固定 | `m5stack/m5gfx: "==0.2.30"`。M5Unified と `esp_websocket_client` も実装時に完全一致で固定し、`dependencies.lock` をコミット |
| パーティション | `nvs` 0x9000 / 0x6000、`phy_init` 0xF000 / 0x1000、`factory` 0x10000 / 4 MB。元の工場データ・NVS 配置との整合は Phase 5 のバックアップ解析で確認し、それまで書き込まない |
| C++ | core は C++17、例外なし・RTTI なし（`-fno-exceptions -fno-rtti`）でホストでも通す |
| ホストテスト | CMake 3.16 以上、`-Wall -Wextra -Werror`、CI では ASan / UBSan 付きでも実行 |
| Python | 3.11 と 3.13 で pytest |
| CI の権限 | `permissions: contents: read`。`pull_request_target` は使わない。外部 action はコミット SHA で固定（既存 workflow と同じ方針） |
| 生成物 | ファームのバイナリは成果物としてアップロードしない（未検証のバイナリを配らない）。サイズ表だけログに出す |

## 5. アバター状態機械

core の `AvatarStateMachine` は時刻と入力イベントを受け、次の状態と「送るメッセージ」「音声の操作」を返す。端末は gateway の `state` を正とし、長押しと端末側の収音停止では gateway の応答を待たずに表示を変える。

| 現在 | 入力 | 次 | 出力 |
| --- | --- | --- | --- |
| 任意 | 接続断（WS 切断・ping 期限・Wi-Fi 断） | Disconnected | 収音停止、再生バッファ破棄 |
| Disconnected | `hello_ok` | Idle | — |
| Disconnected | 長押し | Disconnected | 何も送らない。瞬き 1 回 |
| Idle | 長押し | Listening | `listen_start`、収音開始 |
| Listening | 長押し / VAD 無音 / 5 秒発話なし / 15 秒 | Thinking（gateway の `state` で確定） | `listen_stop`、収音停止 |
| Thinking | 長押し | Idle | `cancel` |
| Thinking | `tts_start` | Speaking | バッファへの格納を開始し、§4.5 の条件で再生 |
| Thinking | Thinking に入ってから 100 秒 | Error → Idle | `cancel` |
| Speaking | 長押し | Idle | `cancel`、再生バッファ破棄、次の `tts_start` までバイナリを捨てる |
| Speaking | `tts_end` かつ再生バッファが空 | 保留中の `state`（通常 Idle） | — |
| 任意（接続中） | `state{error}` / `error{retryable}`（`no_speech` 以外） | Error（最低 1.5 秒） | 収音停止 |
| Error | 1.5 秒経過 | 保留中の `state`（定型音声があれば Speaking、なければ Idle） | — |
| Error | 長押し | Error | 無視 |
| 任意（接続中） | `error{no_speech}` | Idle | Error を出さず瞬き 1 回 |
| 任意 | tap | 変化なし | 視線をタップ位置へ、即座に瞬き |
| 任意 | drag | 変化なし | 視線が指に追従、離したら状態の視線へ戻る |

エラー時の `state{speaking}` と再生は Error の最低表示時間が終わるまで保留する。先に届いた音声と `tts_end` は保持する。再生が終わるまで `state{idle}` は保留する（受信から最大 2 秒。期限に達したらバッファを捨てて適用）。

音声の破棄は二段階で行う（§4.5）。WS 受信キューでは容量を超えた新しい音声フレームを捨てて数え、再生バッファでは容量を超えたとき最古の音声フレームを捨てて数える。どちらも制御イベントの受信順を保ち、接続を維持する。

## 6. プロトコル v1

### 6.1 メッセージ

| type | 方向 | フィールド | 説明 |
| --- | --- | --- | --- |
| `hello` | 端末 → gw | `v`(int=1)、`token`(str)、`fw`(str) | 接続後の最初のメッセージ。5 秒以内 |
| `hello_ok` | gw → 端末 | `v`(int=1) | 認証成功。端末は Idle |
| `auth_error` | gw → 端末 | `code`: `bad_token` / `unsupported_version` | 送ったあと閉じる |
| `listen_start` | 端末 → gw | 任意の `session`（正の整数） | 収音開始。以後のバイナリを発話として受ける |
| `listen_stop` | 端末 → gw | — | 収音終了。gw は即座に `state{thinking}` |
| `cancel` | 端末 → gw | 開始時に付けた `session` | 一致する発話を取り消し、gw は `state{idle}` に同じ番号を付けて返す |
| `state` | gw → 端末 | `state`: `idle` / `listening` / `thinking` / `speaking` / `error`、`session`(正の整数。旧端末では省略可) | 会話状態。端末は現在の番号と異なる通知を捨て、番号のない旧形式も Listening 中は捨てる |
| `tts_start` | gw → 端末 | `sample_rate`(int=16000) | 以後のバイナリは再生音 |
| `tts_end` | gw → 端末 | — | 再生音の終わり |
| `error` | 双方向 | `code`(str)、`retryable`(bool)。gw → 端末の発話中は `session`(正の整数。旧端末では省略可) | 秘密を含まない診断コード。端末は現在の番号と異なる通知を捨て、番号のない旧形式も Listening 中は捨てる |
| `ping` / `pong` | 双方向 | `t`(int、送信側のミリ秒) | `pong` は受けた `t` をそのまま返す |

### 6.2 エラーコード

| code | 方向 | retryable | 意味 |
| --- | --- | --- | --- |
| `no_speech` | gw → 端末 | true | 発話が空（300 ms 未満、または STT 結果が空）。bridge は呼ばない |
| `stt_failed` | gw → 端末 | true | STT の失敗・タイムアウト |
| `bridge_unavailable` | gw → 端末 | true | webhook の送信失敗、gbot がない、mock の失敗 |
| `bridge_timeout` | gw → 端末 | true | 返事が上限内に来ない（`expired`） |
| `reply_error` | gw → 端末 | true | `status: error` の返事 |
| `tts_failed` | gw → 端末 | true | TTS の失敗 |
| `bad_frame` | gw → 端末 | false | 640 バイト以外のバイナリ（そのフレームは捨て、発話は続ける。1 発話につき 1 回だけ通知） |
| `bad_message` | 双方向 | false | 認証後の不正な JSON・必須フィールド欠落 |
| `internal` | 双方向 | true | その他 |

### 6.3 クローズコード

| code | 意味 |
| --- | --- |
| 1000 | 通常終了 |
| 4000 | 版が違う（`auth_error{unsupported_version}` のあと） |
| 4001 | トークン不正（`auth_error{bad_token}` のあと） |
| 4002 | `hello` の期限切れ |
| 4003 | 認証前のプロトコル違反（不正 UTF-8 を含む。応答なし）、またはパーサーのサイズ超過（認証済みなら `error{bad_message}` のあと） |
| 4004 | 新しい接続に置き換えた |
| 4005 | 無通信の期限切れ |

### 6.4 正常系の順序

```
端末                          gateway
hello{v,token,fw}      ──▶
                       ◀──   hello_ok{v}
listen_start           ──▶
                       ◀──   state{listening}
[640B]×N               ──▶
listen_stop            ──▶
                       ◀──   state{thinking}      （STT → bridge → /v1/reply 待ち）
                       ◀──   state{speaking}
                       ◀──   tts_start{sample_rate}
                       ◀──   [640B]×M
                       ◀──   tts_end
                       ◀──   state{idle}          （端末は再生完了後に適用）
```

`no_speech` の場合は `error{no_speech}` → `state{idle}`。ほかの失敗では `state{error}` → `error{code,retryable}` →（定型音声があれば）`state{speaking}`・`tts_start`・音声・`tts_end` → `state{idle}`。

## 7. gateway の処理

### 7.1 `/v1/reply` の検証順と応答

HTTP の形式を検証してから、[webhook ブリッジ仕様 §3](BRIDGE_WEBHOOK.md) の順序で返信を検証する。

1. `Content-Encoding` が `identity` 以外 → 415。自動展開せずに拒否する
2. 受信した body が 8,192 バイトを超える → 413
3. `X-GrokWatch-Request-Id`・`X-GrokWatch-Timestamp`・`X-GrokWatch-Signature` の欠落・形式不正（UUIDv4、整数の UNIX 秒、`sha256=` と 64 桁の 16 進数）、`Content-Type` が `application/json` でない → 422
4. `request_id` が記録にない、または終端状態の保持期間が過ぎている → 404
5. `cancelled`・`expired`、または現在時刻が `expires_at` 以上 → 410。期限に達した `pending` は `expired` にする
6. タイムスタンプが ±120 秒の外 → 401
7. 署名（`HMAC-SHA256(reply_token, timestamp + "." + received_body)`）を定数時間比較。不一致 → 401
8. `answered` の場合: 受信した body の SHA-256 が受理済みと同じ → 200 `{"status":"duplicate"}`、違う → 409
9. UTF-8 の JSON オブジェクトとして読めない、必須フィールド `v`・`request_id`・`status`・`text` に欠落や型違いがある、`v` が整数の 1 以外、body の `request_id` がヘッダと違う、`status` が `ok/declined/error` 以外、`text` が 400 文字超、任意の `emotion`・`end_conversation` の型がそれぞれ文字列・真偽値と違う → 422
10. 受理: `answered` にして 200 `{"status":"accepted"}`。返事を会話に渡す

- `pending` からの遷移は発話ごとに一度だけ確定する。`answered` の `reply_token` は受理済み返信の署名検証にだけ使い、期限に達したら破棄する。同じ body の判定は JSON の再直列化をせず、受信したバイト列で行う。
- `emotion` の省略時は `neutral`。未知の値も `neutral` として扱い、ログには正規化後の値を残す。
- Markdown・URL・絵文字を避ける指示と、返信 POST が 5xx または接続失敗だった場合の再送は伝書鳩側の契約。Phase 5 で確認する。
- `status: declined` は `text` をそのまま読み上げる。`status: error` は `text` があれば読み上げる。返事が空か空白だけなら `reply_error` の定型音声を使う。

### 7.2 発話 1 回の流れ

1. `listen_start`: 前の発話が `pending` なら `cancelled` にする。新しい session を作り `state{listening}`。
2. 音声を受ける。750 フレームに達したら `listen_stop` と同じ扱い（以後のフレームは捨てる）。
3. `listen_stop`: `state{thinking}`。300 ms 未満なら `error{no_speech}` → `state{idle}`。
4. STT。失敗 → `stt_failed`。結果が空白だけ → `no_speech`。
5. bridge の `send_utterance`。webhook は registry に `pending` を作ってから送る。送信失敗 → `pending` なら `cancelled` にし、先に返信が届いていても再生せず `bridge_unavailable`。
6. 返事を待つ。webhook は `created_at` から `GROKWATCH_REPLY_TIMEOUT_S`（既定 90 秒）まで。POST の送信と返信待ちには同じ `expires_at` と registry の時計を使う。POST が未完了でも期限に達したら中断し、`pending` は `expired` にして `bridge_timeout` に進む。
7. `status: error` なら `state{error}` と `error{reply_error}` を先に送る。TTS → `state{speaking}`・`tts_start`・音声・`tts_end`・`state{idle}`。TTS 失敗 → `tts_failed`。
8. どの段階でも `cancel` または切断が来たら、STT・TTS のサブプロセスを止め、registry に `pending` があれば `cancelled` にし、音声の送出をやめて `state{idle}`（切断時は送らない）。

### 7.3 `/healthz`

`GET /healthz` → 200 `{"status":"ok","bridge":{"name":"webhook","available":true},"stt":"mock","tts":"mock","device_connected":false,"version":"0.1.0"}`。URL、キー、トークン、Agent ID、ホスト名、パスは含めない。bridge が `unavailable` なら `bridge.available` は `false`、`status` は `degraded`。

## 8. bridge の契約

```python
class Bridge(Protocol):
    name: str
    async def send_utterance(self, text: str, session: Session) -> AsyncIterator[ReplyChunk]: ...
    async def health(self) -> Health: ...
    async def cancel(self, session: Session) -> None: ...
```

- `ReplyChunk(text, status, emotion, final)`。webhook と gbot_cli は最終断片 1 つを返す。
- 例外: `BridgeUnavailable`（送れない・CLI がない）、`BridgeTimeout`（期限切れ）、`BridgeCancelled`。
- `ReplyInbox`（bridge が定義、gateway の registry が実装）: `open(request_id, reply_token, expires_at) -> Awaitable[Reply]`、`cancel(request_id)`。
- `health()` は外部送信も CLI 起動もしない。秘密を返さない。

| アダプタ | 振る舞い |
| --- | --- |
| `webhook` | BRIDGE_WEBHOOK.md §2 の body とヘッダで 1 回だけ POST（8 秒）。200 で受付、それ以外・タイムアウトは `BridgeUnavailable`（リダイレクトも追わない）。返事は `ReplyInbox` 経由で待つ。`cancel` は inbox を `cancelled` にする（外部ルーチンは止められない）。 |
| `gbot_cli` | `GROKWATCH_GBOT_BIN` を `GROKWATCH_GBOT_ARGS` で subprocess 実行（シェルを使わない）。本文は標準入力。非ゼロ終了・タイムアウト → `BridgeUnavailable`。`cancel` はプロセスを止める。見つからなければ `health()` が `unavailable`。GrokWatch は CLI を同梱しない。 |
| `mock` | 外部送信なし。設定: 固定応答文、遅延秒、失敗（`BridgeUnavailable`）、無応答、`post_reply`（本物の `/v1/reply` へ HMAC 付きで POST）。`post_reply` には試験用の変種（署名改ざん、古いタイムスタンプ、同じ body の 2 回送信、別 body の 2 回送信、取り消し後の送信、`status` 指定）を持つ。 |

## 9. ログと秘密

- gateway は 1 行 1 JSON（`ts`、`level`、`event`、`request_id`、`state`、`http_status`、`latency_ms`、`chars`、`code`）を標準出力へ出す。
- 出さないもの: デバイストークン、`reply_token`、署名、webhook URL・送信キー、Agent ID、ホスト名・IP、家庭内パス、端末固有 ID、音声、本文。本文の記録は既定で無効とし、ローカル調査で `GROKWATCH_LOG_TEXT=1` を明示した場合だけ伏字処理後の本文を出す。
- ログ整形器は設定または発話処理で把握した秘密と端末固有情報の値を `***` に置き換える最後の防壁を持つ。
- ファームのログ（`ESP_LOG*`）にも Wi-Fi パスワード、トークン、SSID を出さない。

## 10. テストの置き場所と実行

| 対象 | 置き場所 | 実行 |
| --- | --- | --- |
| core | `firmware/host_test/test_*.cpp` | `cmake -S firmware/host_test -B build/host && cmake --build build/host && ctest --test-dir build/host --output-on-failure` |
| gateway | `gateway/tests/test_*.py` | `uv run pytest gateway/tests` |
| bridge | `bridge/tests/test_*.py` | `uv run pytest bridge/tests` |
| モック通し | `tests/e2e/test_*.py`（偽デバイスは `tests/e2e/fake_device.py`） | `uv run pytest tests/e2e` |
| リポジトリ衛生 | `tests/repo/test_*.py` | `uv run pytest tests/repo` |
| ファームビルド | `.github/workflows/ci.yml` の `firmware-build` | `idf.py set-target esp32s3 && idf.py build`（`espressif/idf:v5.5.4`） |

- 時刻と乱数は注入する。core は `now_ms` と乱数の種を引数で受ける。gateway はタイムアウト値と時計を設定で差し替え、90 秒などを待たずに試す。
- テストの送信先はローカルの偽サーバに限る。サーバは `127.0.0.1` の空きポートで立てる。whisper.cpp、`say`、`security`、`gbot` はテスト用の偽コマンドに置き換える。
- テストは一時ディレクトリの偽コマンドから `tests/fixtures/fake_command.sh` を呼ぶ。環境変数で出力・終了コード・遅延を切り替える。

## 11. GREEN when（受け入れテスト一覧）

全項目が CI で通ったら Phase 4 完了。各行の条件を以下のテストで判定する。テスト名は案。C++ は `ファイル::TEST名`、Python は `ファイル::関数名`。

### A. core: 状態機械（`firmware/host_test/test_avatar_state.cpp`）

| # | GREEN when | テスト |
| --- | --- | --- |
| A1 | 起動直後は Disconnected。`hello_ok` で Idle になる | `boot_is_disconnected_until_hello_ok` |
| A2 | Idle で長押し → Listening、出力は `listen_start` と収音開始 | `idle_long_press_starts_listening` |
| A3 | Listening で長押し → `listen_stop`、収音停止。`state{thinking}` の受信前に Listening のリングが消え、受信後も Thinking を維持する | `listening_long_press_sends_listen_stop` |
| A4 | Listening で VAD 無音 1,200 ms、5 秒発話なし、15 秒経過のそれぞれで `listen_stop` が 1 回だけ出る | `listening_auto_stop_on_silence_no_speech_and_max` |
| A5 | Thinking で長押し → Idle、`cancel` が出る | `thinking_long_press_cancels` |
| A6 | Speaking で長押し → Idle、`cancel` と再生バッファ破棄。その後 `tts_start` までのバイナリは捨てる | `speaking_long_press_cancels_and_drops_audio` |
| A7 | 正常系の列 Idle → Listening → Thinking → Speaking → Idle を通る。`state{idle}` は再生完了まで保留される | `full_turn_sequence_defers_idle_until_drained` |
| A8 | 再生未完了なら `state{idle}` の受信から 2 秒でバッファを破棄して Idle に遷移する | `deferred_idle_applies_after_2s` |
| A9 | `error{stt_failed}` → Error が 1.5 秒続く。その間に届いた定型音声は保持し、Speaking で再生してから Idle に進む | `error_holds_min_1500ms_then_canned_then_idle` |
| A10 | `error{no_speech}` は Error を出さず Idle、瞬きが 1 回起きる | `no_speech_returns_idle_without_error` |
| A11 | Thinking に入ってから 100 秒で Error → Idle、`cancel` が出る。途中に `pong` や Thinking の再通知があっても同じ | `thinking_local_timeout_100s` |
| A12 | どの状態でも接続断 → Disconnected、収音停止と再生バッファ破棄が出る | `link_down_from_any_state_goes_disconnected` |
| A13 | Disconnected と Error での長押しはメッセージを送らず状態を維持する。Disconnected では瞬きが 1 回起きる | `long_press_when_disconnected_or_error` |
| A14 | Speaking 中の tap は状態を変えず、瞬きと視線の目標だけが変わる。リングは Speaking のまま | `tap_during_speaking_keeps_state` |
| A15 | Speaking 中の drag は視線が追従し、離すと 300 ms で中央へ戻る。状態は Speaking のまま | `drag_during_speaking_keeps_state` |
| A16 | Disconnected で tap は視線移動と瞬き、drag は視線追従を起こす。どちらでも点線リングの点灯・消灯の位相は変わらない | `touch_during_disconnected_keeps_ring` |

### B. core: ジェスチャー（`firmware/host_test/test_gesture.cpp`）

| # | GREEN when | テスト |
| --- | --- | --- |
| B1 | 299 ms・移動 0 で離すと tap、300 ms 以上では tap にならない | `tap_boundary_300ms` |
| B2 | 移動 12 px 以内で 600 ms 押し続けると、離す前に long press が 1 回だけ発火し、離しても tap が出ない | `long_press_fires_once_at_600ms_without_tap` |
| B3 | 13 px 動くと drag 開始、以後 600 ms 経っても long press にならない | `drag_cancels_long_press` |
| B4 | 速いスワイプ（50 ms で 200 px）は drag 開始・移動・終了の列だけを出し、モード切替などの別イベントを出さない | `swipe_is_reported_as_drag_only` |
| B5 | 長押し発火から 800 ms 以内の次の長押しは無視、801 ms 以降は発火 | `long_press_cooldown_800ms` |
| B6 | 同じ押下中に原点から 12 px で drag は始まらず、12 px を超えた最初の点で始まる | `drag_boundary_12px` |

### C. core: 視線と目（`firmware/host_test/test_gaze.cpp`、`test_face_model.cpp`）

| # | GREEN when | テスト |
| --- | --- | --- |
| C1 | 中心 `(233,233)` で `g = (0,0)`、0 除算や NaN が出ない | `gaze_center_is_zero` |
| C2 | 四隅 `(0,0)`・`(465,0)`・`(0,465)`・`(465,465)` と画面外 `(-50,600)`・`(10000,-10000)` で `\|g\| ≤ 1 + 1e-6`、向きは入力方向と一致 | `gaze_clamps_corners_and_offscreen` |
| C3 | 円内の点（`\|u\| < 1`）はクランプされず `g = u` | `gaze_inside_circle_unclamped` |
| C4 | `g_x = +1` のとき右目は幅 `w0×0.75`・高さ `h0×1.15`、左目は幅 `w0×1.25`・高さ `h0×0.85` | `eye_asymmetry_at_right_edge` |
| C5 | `g_x = -1` で C4 の左右が入れ替わる。`g_x = 0` で左右が同じ形 | `eye_asymmetry_mirrors` |
| C6 | 視線ゼロと単位円周上の 360 方向（1° 刻み）で、Listening の高さ倍率を適用した場合も含め、両目の外接矩形の四隅が中心から 196 px 以内 | `eyes_stay_inside_face_all_directions` |
| C7 | 固定の目標に対する 33 ms 後の移動量は、初期差の `1 − exp(−33/80)`（約 33.8%）から ±2 ポイント以内 | `drag_smoothing_time_constant` |
| C8 | 状態の視線を固定して離すと、目標までの距離は増えず、300 ms で目標に到達する | `release_returns_in_300ms` |
| C9 | Idle と Thinking はリングなし。Listening は白・太さ 4、Speaking は太さ `2+8×level`、Error は琥珀・太さ 6。Disconnected は灰色・太さ 4・12 分割で 500 ms ずつ点灯と消灯。表示中のリングは半径 214 px | `face_model_ring_per_state` |
| C10 | Listening の目の高さが Idle の 1.15 倍 | `listening_eyes_taller` |
| C11 | Thinking の視線が周期 2.4 秒・振幅 0.5 で左右に動き、19.9 秒で合図なし、20 秒から下側の 3 点が 600 ms 周期で順に点灯する | `thinking_sway_and_long_wait_hint` |
| C12 | タップから 120 ms で指定位置の視線に到達し、1.5 秒保持してから状態の視線に戻る。整数の座標が得られない更新では直前の視線を保つ | `tap_gaze_timing_and_missing_point` |

### D. core: 瞬き・漂い・音声レベル（`test_blink.cpp`、`test_drift.cpp`、`test_audio_level.cpp`）

| # | GREEN when | テスト |
| --- | --- | --- |
| D1 | 固定の乱数の種 3 通りで Idle と Disconnected を各 10 分模擬すると、自発瞬きの開始間隔がすべて 2,000〜6,000 ms に入る | `idle_and_disconnected_blink_interval` |
| D2 | タップなしで Listening、Thinking、Speaking、Error を各 6 秒超模擬すると、自発瞬きは 0 回 | `no_spontaneous_blink_in_active_states` |
| D3 | タップしたフレームに瞬きが始まり、60〜90 ms は瞬き直前の高さの 0.08 倍、150 ms で元の高さに戻る。同じ入力で全状態を確認する | `tap_blinks_immediately_150ms` |
| D4 | 瞬き中のタップで終了時刻は延びず、次の自発瞬き間隔は注入した乱数で引き直される | `tap_during_blink_does_not_double` |
| D5 | タッチなしの Idle と Disconnected を固定の種 3 通りで各 30 秒模擬する。10 ms 刻みで始まる各 5 秒窓に、先頭からユークリッド距離 0.02 以上のサンプルがある。目標の更新間隔は 1,500〜4,000 ms、半径は 0.35 以下 | `idle_and_disconnected_drift` |
| D6 | 平滑化前の値は RMS 0・3000・6000 以上でそれぞれ 0・0.5・1。段差入力に対する立ち上がりと減衰は §4.3 の時定数 30 ms・120 ms に従う | `audio_level_mapping_and_smoothing` |
| D7 | 再生フレームが途切れると 100 ms 後から減衰し、さらに 200 ms 以内に `level = 0` | `audio_level_decays_when_audio_stops` |
| D8 | VAD は RMS 499 を無音、500 を発話と判定する。発話後の無音 59 フレームでは止めず、60 フレーム目で止める | `vad_thresholds` |

### E. core: 再接続・設定・プロトコル（`test_backoff.cpp`、`test_link_supervisor.cpp`、`test_config.cpp`、`test_protocol.cpp`、`check_core_includes`）

| # | GREEN when | テスト |
| --- | --- | --- |
| E1 | ジッターを 0 にすると待ち時間が 1, 2, 4, 8, 16, 30, 30 秒 | `backoff_sequence_no_jitter` |
| E2 | ジッターありで 1 万回引き、各段の値が基準値 ±20% の範囲かつ 0.8〜30 秒 | `backoff_jitter_bounds` |
| E3 | `hello_ok` 後に失敗すると 1 秒からやり直す | `backoff_resets_after_success` |
| E4 | Wi-Fi 断 → Disconnected、Wi-Fi 復帰 → WS 接続 → `hello` 送信 → `hello_ok` → Idle の順に進む | `wifi_drop_and_recover_to_idle` |
| E5 | gateway 停止（WS 切断）中はバックオフ間隔で再接続を試み、間隔より早く試さない | `gateway_down_retries_on_backoff_schedule` |
| E6 | 25 秒無受信で切断とみなす。24.9 秒ではみなさない。10 秒ごとに `ping` を出す | `ping_interval_and_timeout` |
| E7 | `auth_error` 後は 30 秒間隔で再試行し、Disconnected のまま | `auth_error_retries_every_30s` |
| E8 | 必須設定が空なら「設定なし」で接続しない。既定ポートは 8765 | `config_required_values_and_default_port` |
| E9 | 全メッセージのエンコード結果が 6.1 の形（キー名・型）と一致し、デコードで元に戻る | `protocol_roundtrip_all_types` |
| E10 | 壊れた JSON、`type` なし、必須フィールドの欠落・型違い、入れ子、配列、浮動小数点、4,097 バイト、不正な UTF-8・エスケープはデコード失敗。4,096 バイトの妥当な JSON と正しい Unicode エスケープは受理 | `protocol_rejects_malformed` |
| E11 | 未知の `type` は「未知」として返り、エラーにならない | `protocol_unknown_type_is_ignorable` |
| E12 | トークンに `"` や `\` を含んでもエンコード結果が正しい JSON になる | `protocol_escapes_strings` |
| E13 | 640 バイトちょうどのバイナリだけ音声フレームとして受け、639・641 バイトは捨てる | `audio_frame_size_exact_640` |
| E14 | core のソースが標準ライブラリと `grokwatch/` 以外のヘッダ（`esp_*`、`freertos/*`、`M5*` など）を含まない | `check_core_includes`（ctest に登録した CMake スクリプト） |
| E15 | core が `-fno-exceptions -fno-rtti -Wall -Wextra -Werror` で警告なくビルドでき、ASan / UBSan 付きで全テストが通る | ctest の `host_test_sanitizers` 構成（CI ジョブ） |
| E16 | TTS の 14 フレームでは再生を開始せず、15 フレームで開始する。15 未満でも `tts_end` で残りを再生し、バッファが空になると完了する | `playback_buffer_threshold_and_short_reply` |
| E17 | 1 本の core 受信キューが制御イベントと音声を受信順に返す。最大 32 件の音声を保留し、超過した音声を数えて捨てる。制御イベントの満杯は overflow として返す | `socket_events_keep_their_receive_order`、`audio_overflow_is_counted_and_control_events_keep_their_order`、`control_overflow_is_reported` |

### F. gateway: WebSocket と認証（`gateway/tests/test_ws.py`）

| # | GREEN when | テスト |
| --- | --- | --- |
| F1 | 正しい `hello` で `hello_ok{v:1}` を返す | `test_hello_ok` |
| F2 | トークン不一致で `auth_error{bad_token}` を送り 4001 で閉じる。以後 `state` を送らない | `test_bad_token_closes_4001` |
| F3 | `v: 2` の `hello` で `auth_error{unsupported_version}` と 4000 | `test_unsupported_version_closes_4000` |
| F4 | 認証前の `listen_start`・`ping`・バイナリ・壊れた JSON・不正 UTF-8 テキストのそれぞれで、応答なしに 4003 で閉じる | `test_pre_auth_messages_close_4003`、`test_pre_auth_invalid_utf8_text_closes_4003` |
| F5 | 5 秒（テストでは短縮）以内に `hello` が来なければ 4002 で閉じる | `test_hello_timeout_closes_4002` |
| F6 | 空または 31 文字のトークンでは起動を拒み、32 文字では起動できる | `test_startup_rejects_short_token` |
| F7 | トークン比較が `hmac.compare_digest` 経由（比較関数を差し替えて呼ばれたことを確認） | `test_token_compare_is_constant_time` |
| F8 | 2 本目の接続が認証すると 1 本目を 4004 で閉じる。認証に失敗した 2 本目は 1 本目に影響しない | `test_new_connection_replaces_old` |
| F9 | 30 秒（短縮）無通信で 4005 で閉じ、進行中の発話は `cancelled` | `test_idle_connection_closed_4005` |
| F10 | `ping{t}` に同じ `t` の `pong` を返す | `test_ping_pong` |
| F11 | 認証後の未知の `type` は無視され、接続は続く。壊れた JSON は `error{bad_message}` で接続は続く | `test_unknown_type_ignored_bad_json_reported` |
| F12 | 4,096 バイト超のテキストは認証前に 4003、認証後に `bad_message`。パーサー側で超過を検出した場合は認証後も 4003 で閉じる | `test_oversized_text_frame`、`test_parser_oversize_uses_v1_error_path` |
| F13 | 640 バイト以外のバイナリは捨てられ、`error{bad_frame}` は 1 発話に 1 回だけ。発話は続く | `test_bad_frame_reported_once` |
| F14 | `listen_start` 前と `listen_stop` 後のバイナリは発話に含まれない | `test_frames_outside_listening_ignored` |
| F15 | 749 フレームでは収音中、750 フレーム目で自動で `state{thinking}` になり、751 フレーム目と後着の `listen_stop` で STT は再起動しない | `test_listen_max_750_frames` |

### G. gateway: 会話の流れ（`gateway/tests/test_conversation.py`）

| # | GREEN when | テスト |
| --- | --- | --- |
| G1 | `listen_stop` 直後（STT 完了前）に `state{thinking}` を送る | `test_thinking_sent_before_stt` |
| G2 | 300 ms 未満の発話は `error{no_speech}` → `state{idle}`、STT と bridge を呼ばない | `test_short_audio_is_no_speech` |
| G3 | STT 結果が空・空白だけなら `no_speech`、bridge を呼ばない | `test_empty_transcript_is_no_speech` |
| G4 | STT 失敗で `state{error}` → `error{stt_failed,retryable:true}` → 定型音声 → `state{idle}`。bridge を呼ばない | `test_stt_failure_flow` |
| G5 | bridge の `BridgeUnavailable` で `bridge_unavailable` と定型音声「いま伝書鳩につながらないみたい」の PCM が送られる | `test_bridge_unavailable_flow` |
| G6 | webhook の POST が未完了のまま `created_at` 起点の期限に達したら `expired`、`bridge_timeout`、定型音声、Idle の順に進む | `test_webhook_timeout_uses_created_at` |
| G7 | Thinking 中の `cancel` で `state{idle}` を返す。STT 中ならプロセスが終了して bridge 呼び出しは 0 回、返信待ちなら `pending` が `cancelled` になる | `test_cancel_during_thinking` |
| G8 | Speaking 中の `cancel` で、注入した時刻で 100 ms 以内に音声送出を停止する。`tts_end` は送らず `state{idle}` を返す。受理済みの返信は `answered` のまま | `test_cancel_during_speaking_stops_audio` |
| G9 | 切断で進行中の発話が `cancelled` になり、サブプロセスが残らない | `test_disconnect_cancels_inflight` |
| G10 | `pending` 中の新しい `listen_start` で古い発話が `cancelled` になる | `test_new_listen_cancels_pending` |
| G11 | `declined` と本文付き `error` は本文を再生する。本文が空の `error` は定型音声を送る。`error` のどちらの分岐でも `state{error}` と `error{reply_error}` を先に送る。どちらの `end_conversation` 値でも再生後は Idle に戻る | `test_declined_and_error_reply` |
| G12 | TTS 失敗で `state{error}` → `error{tts_failed}` → `state{idle}`、`tts_start` を送らない。TTS 合成中に取り消した場合はプロセスが終了し、音声を送らない | `test_tts_failure_and_cancel` |
| G13 | `tts_start` の後の最初の最大 10 フレームは待機なし、以後は注入時計で 20 ms ごとに 1 フレーム。すべて 640 バイトで、最後の端数はゼロ埋めする | `test_tts_framing_and_pacing` |
| G14 | 定型音声は起動時に 1 回だけ合成され、以後はキャッシュを使う。TTS が起動時に失敗しても起動でき、失敗時は音声なしで Error → Idle | `test_canned_audio_cache_and_fallback` |

### H. gateway: `/v1/reply`（`gateway/tests/test_reply.py`）

HTTP テストの署名は BRIDGE_WEBHOOK.md §7 の参考手順から独立に計算する。リクエスト送信前の UTF-8 バイト列に署名する。

| # | GREEN when | テスト |
| --- | --- | --- |
| H1 | 正しい署名・期限内で 200 `accepted`、状態が `answered`、会話に返事が渡る | `test_valid_reply_accepted` |
| H2 | 期限内に正しく署名した同じ body の再送で 200 `duplicate`、読み上げは 1 回だけ | `test_duplicate_same_body` |
| H3 | 受理後、空白だけが異なる JSON でも、別のバイト列に正しく署名して送ると 409 | `test_conflicting_body_409` |
| H4 | body を 1 バイト改ざん → 401。署名の 16 進を 1 文字変更 → 401。`sha256=` なし → 422 | `test_bad_signature_401` |
| H5 | 別の発話の `reply_token` で署名 → 401 | `test_wrong_token_401` |
| H6 | タイムスタンプが +121 秒・-121 秒で 401、±120 秒で受理 | `test_timestamp_window_120s` |
| H7 | `expires_at` ちょうどで `pending` に送ると 410、状態は `expired`。受理済み body も期限以後は 410 | `test_expired_410` |
| H8 | 取り消し後（長押しで止めた）の返事は 410、何も読み上げない | `test_reply_after_cancel_410` |
| H9 | 知らない `request_id` で 404。保持 10 分（短縮）を過ぎた記録も 404 | `test_unknown_and_purged_404` |
| H10 | 8,192 バイトの妥当な body は 200、8,193 バイトは 413。超過時は必須ヘッダーがなくても 413 | `test_body_too_large_413` |
| H11 | ヘッダーの欠落・形式不正、Content-Type 違いは 422。正しく署名した JSON の形式・必須項目・型・ID・status 違反と 401 文字の本文も 422。400 文字と任意項目の省略は受理 | `test_malformed_422`（パラメータ化） |
| H12 | 期限内の `answered` への再送は、署名ヘッダーが欠落・形式不正なら 422、形式が正しく署名が違えば 401。形式が正しい署名でも ID 不明は 404、期限切れ・取消済みは 410 を署名照合より先に返す | `test_answered_requires_signature` |
| H13 | 未知の `emotion` は `neutral` として受理 | `test_unknown_emotion_is_neutral` |
| H14 | 署名の比較に `hmac.compare_digest` を使う | `test_signature_compare_constant_time` |
| H15 | `/healthz` は 200 と §7.3 のキー・型を返し、秘密・ホスト名・パスのダミー値を含まない。webhook の URL またはキーがない構成は起動し、`degraded` と `bridge.available: false` を返す | `test_healthz_shape_and_no_secrets` |
| H16 | 返信口は既定で `127.0.0.1:8767` にバインドする。別ポートは指定でき、非ループバックの指定では起動を拒む | `test_reply_listen_default_loopback` |
| H17 | 同一 `pending` に同時に 2 件送ると、`accepted` は 1 件、もう一方は同一 body で `duplicate`、別 body で 409。取消が先なら 410。受理が先なら後から取消しても受理済みのまま。会話への引き渡しは受理時の 1 回だけ | `test_simultaneous_terminal_transition`、`test_reply_and_cancel_follow_first_terminal_transition` |

### I. gateway: STT・TTS・設定・ログ（`gateway/tests/test_providers.py`、`test_logging.py`）

| # | GREEN when | テスト |
| --- | --- | --- |
| I1 | mock STT が設定した文・遅延・失敗を再現する | `test_mock_stt_modes` |
| I2 | whisper.cpp 実装が偽の `whisper-cli` を `-m <model> -f <wav> -l ja -nt -otxt` で呼び、出力ファイルの文を返す。渡す WAV が 16 kHz・モノラル・16 bit | `test_whisper_invocation_and_wav` |
| I3 | `whisper-cli` がない・非ゼロ終了・30 秒（短縮）超えで `SttError`。タイムアウト時にプロセスが残らない | `test_whisper_failures` |
| I4 | 一時ファイル（WAV・出力）が成功時も失敗時も消える | `test_whisper_cleans_temp` |
| I5 | mock TTS が文字数に応じた長さの決まった PCM を返す（同じ文で同じバイト列） | `test_mock_tts_deterministic` |
| I6 | macOS `say` 実装が偽の `say` を `-v Kyoko -f <txt> --file-format=WAVE --data-format=LEI16@16000 -o <wav>` で呼び、引数に本文を含めない。WAV ヘッダを外した PCM を返す | `test_say_invocation_no_text_in_argv` |
| I7 | 偽の `say` の不正な WAV（16 kHz・モノラル・16 bit のいずれかを満たさない）、非ゼロ終了、30 秒の期限切れで `TtsError`。一時ファイルとプロセスが残らない | `test_say_failures_and_cleanup` |
| I8 | `-` で始まる本文、改行・引用符を含む本文でも、引数注入にならない | `test_say_text_injection_safe` |
| I9 | `GROKWATCH_ALLOW_ENV_SECRETS` がなければ環境変数の webhook キーを読まない。Keychain 取得は `security` コマンドの呼び出しとして組み立てられる（Linux では偽コマンド） | `test_secret_sources` |
| I10 | 正常・異常経路のログに、注入したトークン、署名、webhook URL・キー、Agent ID、ローカル IP、家庭内パス、端末固有 ID のダミー値が含まれない | `test_logs_never_contain_secrets` |
| I11 | 設定なしと `GROKWATCH_LOG_TEXT=0` では発話・返事の本文がログに出ず、`1` で伏字処理後の本文が出る。音声データはいずれでも出ない | `test_log_text_toggle` |
| I12 | ログの各行が JSON として読め、`event`・`request_id`・`latency_ms` を持つ | `test_log_lines_are_json` |

### J. bridge（`bridge/tests/test_adapters.py`）

| # | GREEN when | テスト |
| --- | --- | --- |
| J1 | `GROKWATCH_BRIDGE` で選んだ各アダプタに共通契約の 3 操作を実行できる。未設定時は webhook、未知の名前は起動時エラー | `test_factory_selects_adapter` |
| J2 | `health()` が外部送信も subprocess 起動もせず、戻り値に秘密を含まない（3 アダプタとも） | `test_health_has_no_side_effects` |
| J3 | webhook の POST が BRIDGE_WEBHOOK.md §2 のヘッダー名・値、body のキー・型を持つ。`v: 1`、`type: utterance`、`turn: 1`、§4.8 の `lang`・`max_chars` を確認し、音声・返信先 URL・Agent ID がないことを確かめる | `test_webhook_request_shape` |
| J4 | 1,001 文字は最多 1,000 文字に切る。多バイト文字とエスケープを多く含む文字列も元の文の接頭辞を保持し、送信された UTF-8 JSON は 4,096 バイト以下 | `test_webhook_body_limits` |
| J5 | ローカルの偽サーバが応答を返さないと `BridgeUnavailable`、POST は 1 回だけ、inbox は `cancelled`。クライアントの既定タイムアウトは 8 秒と確認し、実際の待ちは短縮する | `test_webhook_timeout_8s_no_retry` |
| J6 | 201・302・404・500・接続拒否のどれでも送信は 1 回だけで `BridgeUnavailable`、inbox は `cancelled` | `test_webhook_failure_no_retry` |
| J7 | POST を受けた偽サーバが HTTP 200 の前に返信を渡せるよう、inbox を先に登録する。200 後に `send_utterance` は最終断片を 1 つ返す | `test_webhook_yields_reply_from_inbox` |
| J8 | `cancel` で待ちが `BridgeCancelled` で終わり、以後の返事を採用しない | `test_webhook_cancel` |
| J9 | 発話ごとに異なる UUIDv4 と 32 バイト相当の base64url トークンを発行する。新しい長押しで新しい session を作る。RFC 3339 の期限と作成時刻の差は既定で 90 秒、設定時は指定秒数 | `test_webhook_ids_and_expiry` |
| J10 | `gbot` が PATH にないとき `health()` が `unavailable`、`send_utterance` が `BridgeUnavailable` | `test_gbot_missing_unavailable` |
| J11 | 偽の `gbot` に本文が標準入力で渡り、引数は `GROKWATCH_GBOT_ARGS` の展開どおり（シェルを介さない）。標準出力が返事になる | `test_gbot_invocation` |
| J12 | 偽の `gbot` の非ゼロ終了・タイムアウトで `BridgeUnavailable`、プロセスが残らない。`cancel` でプロセスが止まる | `test_gbot_failures_and_cancel` |
| J13 | `gbot_cli` のログ・例外文に Agent ID が出ない | `test_gbot_hides_agent_id` |
| J14 | mock が固定応答・遅延・失敗・無応答を再現する | `test_mock_modes` |
| J15 | mock の `post_reply` が本物の reply サーバへ正しい HMAC で POST し 200 `accepted` を得る。改ざん・古いタイムスタンプ・同一 body の二重送信・別 body の二重送信・取り消し後の各変種で 401・401・`duplicate`・409・410 を得る | `test_mock_post_reply_variants` |
| J16 | `signing.py` の署名が BRIDGE_WEBHOOK.md §7 の参考スクリプトと同じ値になる（同じ入力で一致） | `test_signing_matches_reference` |

### K. モック通し（`tests/e2e/test_mock_roundtrip.py`）

偽デバイスは aiohttp の WS クライアントを使う。gateway は mock STT、mock TTS と、ローカルの `/v1/reply` へ POST する mock bridge を使う。待ち時間は短縮し、各シナリオに 10 秒のテスト期限を設ける。

| # | GREEN when | テスト |
| --- | --- | --- |
| K1 | 正常系: §6.4 の順で状態とメッセージを受信する。`tts_start` と `tts_end` の間で 640 バイトのフレームを 1 個以上受信し、結合結果が mock TTS の PCM を末尾ゼロ埋めしたバイト列と一致 | `test_happy_path_states_and_audio` |
| K2 | 全ゼロの PCM と空文字を返す mock STT: `state` 列が `listening, thinking, idle`、`error{no_speech}`、音声なし、bridge 呼び出し 0 回 | `test_silence_no_speech` |
| K3 | STT 失敗: `listening, thinking, error, speaking, idle`、`error{stt_failed}`、定型音声 | `test_stt_failure_roundtrip` |
| K4 | webhook 失敗（mock の失敗）: `error{bridge_unavailable}`、定型音声、`idle` | `test_bridge_failure_roundtrip` |
| K5 | 返事の遅延 3 秒: その間 `thinking` のまま、他の `state` が来ない。その後通常どおり読み上げ | `test_delayed_reply_stays_thinking` |
| K6 | 返事の期限切れ（上限 1 秒・mock 無応答）: `error{bridge_timeout}` → 定型音声 → `idle`。その後に mock が送った返事は 410 | `test_reply_timeout_then_late_410` |
| K7 | Thinking 中に `cancel`: `idle` を受け、遅れて届いた返事は 410、2 秒待っても `tts_start` が来ない | `test_cancel_then_late_reply_410` |
| K8 | Speaking 中に `cancel`: `idle` を受信し、以後は音声・`tts_end` を受信しない | `test_cancel_during_speaking_roundtrip` |
| K9 | mock が同じ返事を 2 回 POST: 2 回目は `duplicate`、`tts_start` は 1 回だけ | `test_duplicate_reply_spoken_once` |
| K10 | mock が署名を改ざん: 401、返事の本文は再生せず、期限に `bridge_timeout` と定型音声 | `test_tampered_reply_ignored` |
| K11 | 認証失敗: 誤ったトークンで `auth_error` と 4001、`state` を 1 つも受けない | `test_auth_failure_roundtrip` |
| K12 | 認証前の `listen_start` で 4003、応答なし | `test_pre_auth_message_closed` |
| K13 | gateway 再起動: 偽デバイスが core と同じバックオフ表（ジッター 0、短縮倍率）で再接続し、再認証して `hello_ok`。再起動前の発話の返事は届いても読み上げない（404） | `test_gateway_restart_reconnect` |
| K14 | 発話中に偽デバイスが切断 → 再接続: 古い発話は `cancelled`、新しい発話は正常に通る | `test_device_drop_mid_turn` |
| K15 | `/healthz` が mock 構成で `ok`、`device_connected` が接続に合わせて変わる | `test_healthz_during_roundtrip` |
| K16 | 全シナリオの標準出力・標準エラーにトークン、送信キー、署名、URL が出ない | `test_mock_roundtrip.py` の `gateway` fixture |

### L. ファームビルド・CI・リポジトリ（`.github/workflows/ci.yml`、`tests/repo/`）

| # | GREEN when | テスト |
| --- | --- | --- |
| L1 | `espressif/idf:v5.5.4` で `idf.py set-target esp32s3 && idf.py build` が終了コード 0。`sdkconfig.local.defaults` がなくても通る | CI `firmware-build` |
| L2 | 依存解決で M5GFX は 0.2.30、M5Unified と `esp_websocket_client` は §4.11 で固定した版。Git が `firmware/dependencies.lock` を追跡し、ビルド後の lock に差分がない | CI `firmware-build`（`git ls-files --error-unmatch firmware/dependencies.lock` と `git diff --exit-code -- firmware/dependencies.lock`） |
| L3 | ビルドしたパーティション表は §4.11 のオフセット・サイズと一致し、OTA 領域はない。生成したアプリのファイルサイズが factory の 4 MB 以下。CI はサイズを記録し、バイナリをアップロードしない | CI `firmware-build` と workflow の静的検査 |
| L4 | ホストテストのジョブ（通常・サニタイザ）が通る | CI `host-tests` |
| L5 | Python 3.11 と 3.13 の両方で `uv.lock` を使い、gateway・bridge・e2e・repo の pytest が通る。全対象に適用するガードでループバック以外への接続を失敗させ、偽コマンドはネットワークを使わない | CI `python`、共通 pytest fixture |
| L6 | 既存の `secrets-pii.yml` が新ファイルを含めて成功する。許可形式の追加後も秘密・個人情報の検出を確認する。検査対象と終了コードを確認でき、ステージ済み差分と履歴を `bash scripts/scan_secrets.sh` で検査できる | CI `secrets-pii.yml`、検査スクリプトの試験 |
| L7 | すべての workflow の `permissions` が `contents: read` だけで、`pull_request_target` がなく、`uses:` がコミット SHA で固定 | `tests/repo/test_workflows.py::test_permissions_and_pinning` |
| L8 | `sdkconfig.defaults` と `Kconfig.projbuild` の Wi-Fi・ホスト・トークンの既定値が空 | `tests/repo/test_firmware_config.py::test_no_secret_defaults` |
| L9 | `.gitignore` が `sdkconfig.local.defaults`・`build*/`・`managed_components/`・`.env` を含み、それらが追跡されていない | `tests/repo/test_gitignore.py::test_local_files_ignored` |
| L10 | ファームは NVS を使わない（読み取り・書き込みともなし）。`firmware/main` と core に `nvs_*` の呼び出し、および `esp_partition_*`、`spi_flash_*`、`esp_flash_*` の消去・書き込み呼び出しがない | `tests/repo/test_firmware_config.py::test_no_nvs_or_flash_mutation_calls` |
| L11 | ファームのソースの `ESP_LOG*` 呼び出しの引数に `password`・`token`・`ssid` を含む識別子がない | `tests/repo/test_firmware_config.py::test_no_secret_logging` |
| L12 | 形式許可リストで画像・動画と対象外の形式の追跡を拒む。CSV・lock・defaults は `firmware/partitions.csv`、`uv.lock`、`firmware/dependencies.lock`、`firmware/sdkconfig.defaults` のみ許可する | `tests/repo/test_assets.py::test_asset_allowlist` |
| L13 | `netTask`、`buttonTask`、`renderTask`、`audioTask` の主な経路が `app_main.cpp` のタスク枠内に収まり、通常関数は 2,048 B 以下、`audioTask` は 3,072 B 以下 | `scripts/check_stack_frames.py` と `tests/repo/test_stack_frames.py` |

### タスクのスタック予算

`scripts/check_stack_frames.py` は ELF を `xtensa-esp32s3-elf-objdump -dC` で読み、`entry a1, N` の N を関数の枠として扱う。`gwapp::` と `grokwatch::` の各関数には 2,048 B の上限を置く。`audioTask` は `Capture` と `Playback` の状態をループ間で保つため、3,072 B を例外上限にする。タスク枠は `app_main.cpp` の `xTaskCreate` から読む。

net の余裕は 3,072 B で、診断ログの `_vfprintf_r` と Wi-Fi・FreeRTOS の呼び出し分を見込む。buttons、render、audio の余裕はそれぞれ 2,048 B、2,048 B、3,072 B である。表の測定枠は検査対象の C++ 関数枠の合計で、余裕を足した値を各タスクの枠と比べる。

検査器はコードに列挙した主要経路を合計する。間接呼び出しや IDF・ライブラリ内部の全経路は解析しない。余裕はそれらの枠を個別に測った値ではない。実機の実使用量は `diag stack net free=%u` の high-water 値で確認する。

| タスク | 最大の列挙経路 | 関数枠 | 余裕 | 検査値 | `xTaskCreate` 枠 |
| --- | --- | ---: | ---: | ---: | ---: |
| net | JSON エスケープ解析 | 2,000 B | 3,072 B | 5,072 B | 12,288 B |
| buttons | 音量ボタン処理 | 144 B | 2,048 B | 2,192 B | 3,072 B |
| render | 表情計算 | 960 B | 2,048 B | 3,008 B | 6,144 B |
| audio | 再生バッファ排出待ち | 2,880 B | 3,072 B | 5,952 B | 6,144 B |

overflow の原因は `Network` を `netTask` のローカル変数にしていたことだった。中の `Socket` は 4,096 B のテキストバッファと 768 B のイベントキューを持ち、旧 ELF の `netTask` 枠は 7,792 B だった。さらに `diagScan` の AP 記録配列は 1,920 B を使った。診断走査経路は余裕を含めて 13,232 B となり、タスク枠の 12,288 B を超えた。

修正後は `Network` と AP 記録配列を静的領域へ移した。`netTask` は 144 B、`diagScan` は 80 B になり、診断走査経路は 3,744 B になった。Wi-Fi 診断走査のあとと WebSocket 初回接続時に `diag stack net free=%u` を記録する。ESP-IDF の `uxTaskGetStackHighWaterMark` は残量をバイトで返す。実機での残量は未確認である。

素材や顔データの出所・権利、形式不明の Agent ID、個人情報は公開前の差分目視でも確認する（[AGENTS.md](../AGENTS.md)、[LESSONS.md](../LESSONS.md)）。

## 12. 実機でしか確かめられないこと（Phase 5 用）

Phase 5 の端末確認は、対象と影響の承認を得てから進める。書き込み前にフラッシュ全体をバックアップし、機種とパーティション配置を確かめ、C152 用と確認できたバイナリだけを書き込む。Mac mini の確認は別途指示を受ける。結果は [テスト報告](TEST_REPORT.md) に、ビルド結果とは分けて記録する。

### 端末

- 固定した M5Unified と M5GFX 0.2.30 で C152 を正しく検出・初期化できるか（CO5300 QSPI、CST820B、ES8311、AW8737A、M5PM1、M5IOE1）。対象機のハードウェア版（v1.0 / v1.0.1）。
- 画面の向き・色・円の位置、白円と目の見た目、AVATAR_SPEC の受入確認（四方向と中央のタップ、縁の一周、指の解放、長押し）。
- Idle を 30 秒以上撮影し、静止しないこと（撮影ログは非公開で保管）。描画 fps、CPU 使用率、ヒープ・PSRAM 使用量の実測と性能目標の設定。
- タッチ座標と画面座標の対応、ジェスチャーのしきい値（tap 300 ms、long press 600 ms、12 px、800 ms 間隔）の手触り。タッチが途切れたときに解放を取得でき、再押下が正しく反応するか。
- マイクの感度とノイズ、VAD のしきい値（RMS 500、無音 1,200 ms、5 秒）の妥当性。
- スピーカーの音量・歪み・日本語の聞き取りやすさ、再生バッファ 300 ms で途切れないか。Speaking 中にマイクが自分の声を拾わないか。
- 通信停止後に音声がまとめて届いても、再生バッファ満杯で切断せず、最古のフレームを捨てて破棄数を記録するか。
- Speaking のリングが声に合って見えるか（振幅の換算 6000、平滑化の値）。
- 各状態の見分けやすさ（Listening と Thinking、Error と Disconnected）。
- 音声応答中・Wi-Fi 切断中のタッチで、視線が追従し状態表示が保たれるか。
- NVS 無効での Wi-Fi 初期化と接続、実際の AP の切断・復帰、gateway の再起動からの復旧、長時間（数時間）の連続稼働でのメモリリークと再接続。
- AMOLED の休止・復帰、消費電力、電池の持ち、発熱。
- パーティション配置と元の NVS・工場データとの整合、書き込み前のフル バックアップ、失敗時の復旧手順（全面消去しない）。

### Mac mini と伝書鳩

- whisper.cpp のモデル選定、日本語の認識精度と処理時間。
- macOS `say` の日本語音声（Kyoko 等）の有無、16 kHz への直接出力の可否と音質。
- Keychain からの秘密の取得、LAN からの WS 接続とファイアウォール。
- 本物の webhook ルーチンの起動にかかる時間と利用量、`tailscale serve` 経由で伝書鳩のコンピューターから `/v1/reply` へ届くか、伝書鳩が指定どおりに署名し、接続失敗・5xx だけを 2 秒後と 5 秒後に再送するか。Markdown・URL・絵文字を含めずに返信するか。
- 伝書鳩経由で既存の記憶・Skills が使えるか、外に影響する操作が `declined` になるか。
- 待ち時間の仮の値（Thinking の合図 20 秒、上限 90 秒、端末の安全上限 100 秒）の見直し。
- 任意: 利用者が入れた `gbot` での `gbot_cli` の動作。

## 13. 未決とリスク

| 項目 | 内容 | 扱い |
| --- | --- | --- |
| M5Unified の C152 対応 | GrokWatch は M5Unified 0.2.17、M5GFX 0.2.30、`esp_websocket_client` 1.6.1 を使用する | ESP-IDF v5.5.4 と固定依存で Linux 開発機ビルドを確認済み。Phase 5 で実機の初期化・音声を確認する |
| 依存の版 | ESP-IDF v5.5.4、M5Unified 0.2.17、M5GFX 0.2.30、`esp_websocket_client` 1.6.1 | `firmware/dependencies.lock` の固定版を使い、manifest と lock を合わせて更新する |
| LAN の平文 WS | デバイストークンが LAN 上を平文で流れる | v1 は LAN 限定・トークン 32 文字以上。wss は Phase 6 以降に検討 |
| ローカル設定ファイル名 | 当初案の名前が PII 検査に一致するため `sdkconfig.local.defaults` に変更 | オーナー確認 |
| `end_conversation` と `turn` | Phase 3〜4 の v1 は BRIDGE_WEBHOOK.md §5 の会話継続を見送り、`end_conversation` の値にかかわらず再生後は Idle に戻る。`turn` は 1 | 会話の継続は Phase 6 以降に検討 |
| `emotion` | v1 では端末へ送らない | プロトコル v2 で検討 |
| 数値 | 本書の時間・しきい値・寸法は実機で未評価。端末の 100 秒は STT や TTS の時間も含むため、webhook 側の 90 秒より先に打ち切る場合がある | Phase 5 で区間ごとの所要時間を測り、上限を見直す |

## 14. 音量ボタンとアバターの大きさ

A ボタン（黄、GPIO2）で音量を上げ、B ボタン（青、GPIO1）で下げる。物理配置に対する割り当ての手触りは実機で未確認。ボタンは `gpio_get_level` で読み、10 ms 周期で3サンプル安定した入力を確定する。音量ボタンを会話ジェスチャーへ渡さず、電源ボタンの処理も変えない。

音量段 `k` は0〜51の52段階です。`M5.Speaker.setVolume` に渡す master 値は `v=5k` で、段0は無音です。既定は段26、値130、約−11.8 dBです。段51は値255、約−0.14 dBです。押下判定時に1段変わり、400 ms後から200、160、130、100、80、60、50 ms間隔で連続して変わります。上限は毎秒20段で、値0から255までは約3.3秒です。段51と段0では停止し、折り返しません。両方を押すと、両方を離すまで操作を止めます。

| 段 | 0 | 1 | 2 | 4 | 5 | 10 | 13 | 26 | 39 | 50 | 51 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| master値 | 0 | 5 | 10 | 20 | 25 | 50 | 65 | 130 | 195 | 250 | 255 |
| 利得 | 無音 | −68.4 dB | −56.4 dB | −44.4 dB | −40.5 dB | −28.4 dB | −23.9 dB | −11.8 dB | −4.8 dB | −0.48 dB | −0.14 dB |

音量値に応じて顔、目、リング、点を画面中心から拡大縮小する。顔の半径は `200 × sqrt(0.1 × 233² / 200² + (1 − 0.1 × 233² / 200²) × v / 255)` です。値0、130、255の半径は約73.7、151.8、200 pxです。確認音、音量バー、NVSへの保存は行いません。

段とボタンの時間状態、利得、顔の描画寸法は `grokwatch_core` が持ちます。スピーカーとマイクのAPI呼び出しは `audio_task.cpp` に集め、録音開始前にスピーカーを停止します。

M5Unified 0.2.17 の `Speaker.begin()` は、電源 callback の後で I2S 設定に失敗すると callback を戻さず I2S を解除しません。失敗後に残るコーデック電源と部分 I2S を解放するため、`firmware/CMakeLists.txt` は `Speaker_Class.cpp` のビルド用コピーだけを変更し、callback を false で呼び、I2S を解除して false を返します。この変更は依存コンポーネントのファイルに触れません。`firmware/CMakeLists.txt` の M5Unified パッチ節を削除すると、ビルドは元のライブラリソースへ戻ります。失敗経路は実行しておらず、実機でも確認していません。

`playRaw` が false を返した場合、`audio_task.cpp` は `fault(app)` の前に `stop()` を呼びます。失敗した再生を止めるための処理です。失敗分岐の `stop()` を削除すると以前の動作に戻ります。この失敗経路も実行しておらず、実機では確認していません。

ホストテストは段、利得、10 ms 周期のデバウンス、初回遅延、加速、上限、端、両押しを検査します。6つの状態で指定された6つの経過時間について、目・リング・点の境界条件を検査します。§5.2 の目、リング、点の寸法表は5つの音量値と6つの経過時間で照合します。実機の音量、歪み、電池、表示の手触り、タッチとの同時操作、電源ボタン、録音と再生の切り替えは未確認です。結果は[テスト報告](TEST_REPORT.md)の自動検証と実機確認を分けて記録します。
