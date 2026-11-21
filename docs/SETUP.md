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

## Mac mini の導入物

Phase 6 で、下記の動作と導入手順を確認してから配置します。

- Python 3.11 または 3.13、uv 0.13.9、`uv.lock` の依存関係
- whisper.cpp の `whisper-cli` と日本語認識に使うモデル
- macOS の `say` と日本語音声。既定の音声名は `Kyoko`
- macOS Keychain と `security`。デバイストークンおよび webhook の URL とキーを登録
- LAN 上のデバイス WebSocket を受けるファイアウォール設定
- Tailscale と `tailscale serve` を使う返信経路、伝書鳩側の webhook ルーチン
- 任意の非公式 `gbot` CLI。利用者が別途導入し、アプリのセッションを用意
