# 環境

## 開発用 Linux 機のビルド環境

2026-11-21 JST の調査時点。

| 項目 | 調査結果 |
| --- | --- |
| CPU | x86_64、8 コア |
| メモリ | 15 GB |
| ストレージ空き | 100 GB |
| Python | 3.13.5 |
| Node.js | v24.22.1 |
| uv | あり |
| Docker | なし |
| sudo | 利用可 |
| ESP-IDF | 2026-11-21 JST に開発用 Linux 機で v5.5.4 の `install.sh esp32s3` 完了を確認。 |
| GitHub CLI | 未ログイン。 |
| gitleaks | 8.30.1 |

2026-11-21 JST に開発用 Linux 機で groki-bot の `BOARD=stopwatch` を検証目的でビルドした。初回は managed component の `m5stack/m5gfx` が 0.3.0 に解決され、`esp_psram.h` が見つからず失敗した。`main/idf_component.yml` で M5GFX を `==0.2.30` に固定するとビルドに成功し、`stackchan_idf.bin`（約 2.8 MB）が生成された。これは上流のビルド再現であり、GrokWatch のビルドと実機動作は未検証。

## Mac mini

別のエージェントが 2026-11-21 19:39〜19:45 JST に実施した読み取り専用監査の要約。GrokWatch の作業者は Mac mini に触れていない。

| 項目 | 調査結果 |
| --- | --- |
| macOS / CPU | macOS 27.2、Apple Silicon（arm64、12 コア）、メモリ 16 GB、ディスク空き約 53 GB |
| Git | 2.54.0（Apple Git） |
| Homebrew | 7.0.12 |
| uv | なし |
| Python | 既定の python3 は 3.9.6（システム）。Homebrew の 3.14.7 もあるが PATH ではシステム版が先 |
| Node.js | v24.22.2、npm 11.19.1 |
| ESP-IDF / esptool / PlatformIO / Arduino CLI | どれもなし |
| Xcode | 27.1、Command Line Tools 27.2 |
| Grok Bot アプリ | 1.2.3（URL スキーム `grokbot://` と `sand://`）。PATH 上の CLI はなし。アプリが待ち受けるローカルポートはなし |
| Agent ID | 対象は「伝書鳩」。値は公開しない（`.env` の `GROKWATCH_AGENT_ID`） |
| LAN | LAN（種別は記録しない）と Tailscale |
| ポート | 既存サービスが使うポートがある。GrokWatch の既定ポート（8765 / 8767）とは重ならない |
| LaunchAgent / 常駐 | 既存の自作サービスと Bot 関連の常駐がある。GrokWatch はこれらを止めない・変えない |
| USB 接続 | Espressif 内蔵 USB Serial/JTAG（CDC ACM）の機器が外付け USB ハブ経由で 1 台見える。ノード名は `/dev/cu.usbmodem*` の形。ESP32-S3 / C3 / C6 で共通の ID のため、この情報だけでは StopWatch C152 とは確定できない。ポートを開いているプロセスはなし。ノード名は差し直しで変わり得るので Flash 前に再確認する。書き込みは未実施 |

### この結果から分かること

- Mac mini にはファームのビルド環境がない。ファームのビルドは開発用 Linux 機で行う。Mac mini に書き込みツールを導入するかはオーナーの確認後に決める。
- Gateway は Python で動かす想定。Mac mini の既定 python3 は 3.9 なので、uv か Homebrew の Python を使う。uv の導入も確認後。
- Grok Bot アプリ 1.2.3 はローカルの待ち受け口を持たない。groki-bot の内部 RPC 連携は 0.71.2 で試されたもので、1.2.3 での互換性は未確認。
