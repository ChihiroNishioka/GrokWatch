# セットアップ

## Linux 開発機でテストする

Git、CMake 3.16 以上、ASan と UBSan を使える GCC、Python 3.11 と 3.13、uv 0.13.9 を用意します。以下はリポジトリのルートから実行します。

```bash
cmake -S firmware/host_test -B build/host
cmake --build build/host --parallel
ctest --test-dir build/host --output-on-failure

cmake -S firmware/host_test -B build/host-sanitized -DGROKWATCH_SANITIZERS=ON
cmake --build build/host-sanitized --parallel
UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/host-sanitized --output-on-failure

uv run --locked --all-packages --python 3.11 pytest gateway/tests bridge/tests tests/e2e tests/repo
uv run --locked --all-packages --python 3.13 pytest gateway/tests bridge/tests tests/e2e tests/repo
```

ゲートウェイの起動とヘルスチェックは [モック起動手順](../gateway/README.md) を参照してください。

## C152 向けファームウェアをビルドする

ESP-IDF v5.5.4 と ESP32-S3 ツールチェーンを用意します。ESP-IDF v5.5.4 の `export.sh` を読み込んでから実行します。既に `esp32s3` を設定した作業ツリーでは `idf.py set-target esp32s3` を省略できます。

```bash
(
  cd firmware
  idf.py set-target esp32s3
  idf.py build
)
python scripts/check_firmware_build.py
git diff --exit-code -- firmware/dependencies.lock
```

生成したアプリは `firmware/build/grokwatch.bin` です。秘密を含まないビルドには既定の `sdkconfig.defaults` を使います。個別設定が必要なビルドでは、Git 管理外の `firmware/sdkconfig.local.defaults` に設定します。既存の `firmware/sdkconfig` には前回の設定が残るため、defaults を変えた場合はビルド前に設定を生成し直します。ファームは NVS を使わず、読み取りも書き込みも行いません。Wi-Fi と PHY の NVS 保存は無効です。端末への書き込みは [Phase 5 の手順](FLASHING.md) を参照してください。

## Mac mini に Gateway を設置する

**Mac mini への導入と設定変更は、オーナーの承認後に行います。** この節は手順だけを記録します。ここで実機や Mac mini に変更は加えていません。

### 前提ツールを用意する

1. Xcode Command Line Tools と CMake を用意します。

   ```bash
   xcode-select --install
   brew install cmake
   ```

2. uv 0.13.9 と Python 3.11 を用意します。公式の[バージョン固定インストーラー](https://docs.astral.sh/uv/getting-started/installation/)を使い、起動前に版を確認します。

   ```bash
   curl -LsSf https://astral.sh/uv/0.13.9/install.sh | sh
   uv --version
   uv python install 3.11
   ```

3. whisper.cpp の `whisper-cli` をビルドし、日本語向けの `base` モデルを保存します。公式の [whisper.cpp ビルド手順](https://github.com/ggml-org/whisper.cpp#quick-start)と[モデル取得スクリプト](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md)を使います。Whisper のコードとモデルは [MIT License](https://github.com/openai/whisper/blob/main/LICENSE) で配布されています。

   ```bash
   git clone https://github.com/ggml-org/whisper.cpp.git
   cd whisper.cpp
   cmake -B build
   cmake --build build -j --config Release --target whisper-cli
   mkdir -p "$HOME/.local/bin" "$HOME/.local/share/GrokWatch/models"
   install -m 755 build/bin/whisper-cli "$HOME/.local/bin/whisper-cli"
   ./models/download-ggml-model.sh base "$HOME/.local/share/GrokWatch/models"
   whisper-cli --help
   ```

   インストールした実行ファイルは LaunchAgent の PATH から使えます。モデルはリポジトリの外に置きます。

4. Confirm that macOS provides the Kyoko voice.

   ```bash
   say -v '?' | grep -w Kyoko
   say -v Kyoko '音声の確認です'
   ```

### Keychain に秘密を登録する

Gateway は `grokwatch` サービスの Keychain から秘密を読みます。アカウント名と `security` の使い方は[Keychain の設定](../deploy/macos/keychain.md)を参照してください。デバイストークンを保護した一時ファイルに作り、登録後にファイルを削除します。

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TMPDIR/gw-device-token"
chmod 600 "$TMPDIR/gw-device-token"
bash deploy/macos/keychain-add.sh --file "$TMPDIR/gw-device-token" GROKWATCH_DEVICE_TOKEN
rm -f "$TMPDIR/gw-device-token"
```

承認された経路で webhook URL とキーを受け取った後、同じ補助スクリプトで登録します。秘密の値をコマンド引数、端末出力、シェル履歴、リポジトリのファイルに置かないでください。項目の有無は `-w` を付けずに確認します。

```bash
security find-generic-password -s grokwatch -a GROKWATCH_DEVICE_TOKEN
security find-generic-password -s grokwatch -a GROKWATCH_WEBHOOK_URL
security find-generic-password -s grokwatch -a GROKWATCH_WEBHOOK_KEY
```

### Mock bridge で起動する

オーナーの導入承認後、リポジトリのルートから実行します。インストーラーが扱う LaunchAgent は `com.grokwatch.gateway` だけです。8765 または 8767 番ポートを別プロセスが使っている場合は停止します。

```bash
bash deploy/macos/install.sh --bridge mock \
  --whisper-model "$HOME/.local/share/GrokWatch/models/ggml-base.bin"
bash deploy/macos/status.sh
curl --fail --silent http://127.0.0.1:8767/healthz
```

`status.sh` prints the LaunchAgent state, ports, health response code, Keychain item presence, and Tailscale Serve state. The mock bridge does not require webhook Keychain items.

Mac mini 上で偽デバイスから Gateway までの疎通を確認するには、既存の end-to-end テストを実行します。テストは専用のモック Gateway を起動し、実機には接続しません。

```bash
uv run --locked --all-packages --python 3.11 pytest tests/e2e
```

### Webhook と Tailscale Serve に切り替える

モックで確認した後、webhook 用の Keychain 項目を 2 つ登録し、同じ LaunchAgent を更新します。

```bash
bash deploy/macos/install.sh --bridge webhook \
  --whisper-model "$HOME/.local/share/GrokWatch/models/ggml-base.bin"
bash deploy/macos/status.sh
```

[Tailscale Serve の設定](../deploy/macos/tailscale-serve.md)に従い、tailnet には `/v1/reply` だけを公開します。この手順には Funnel が有効でないことの確認と Serve 経路の解除方法も記載しています。

### Gateway をアンインストールする

アンインストールでこの LaunchAgent と plist を削除します。ログと Keychain 項目は残します。

```bash
bash deploy/macos/uninstall.sh --dry-run
bash deploy/macos/uninstall.sh
```

失効させる場合に限り、Keychain 項目を手動で削除してください。`security delete-generic-password` の使い方は Keychain のガイドを参照します。
