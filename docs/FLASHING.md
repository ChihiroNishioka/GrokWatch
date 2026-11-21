# Phase 5 の書き込みと復旧

**承認を得てから実行します。** 対象機種とハードウェア版、使用する USB ポート、バックアップの保存先、書き込み範囲、データへの影響、復旧方法を示してください。書き込みと復旧書き込みはそれぞれ承認を得ます。この手順は実機未検証です。

## 対象を確認して全フラッシュを控える

1. 本体が M5Stack StopWatch C152 であることと、ハードウェア版を確認します。データ通信対応の USB-C ケーブルで接続します。電源ボタンを長押しし、緑 LED が点滅したら離します。接続前後の `/dev/cu.usbmodem*` を比較し、この端末のポートを一つ選びます。[M5Stack の StopWatch 仕様](https://docs.m5stack.com/en/core/StopWatch)
2. ESP-IDF v5.5.4 の環境を有効にし、`port` を選んだポートの実値に置き換えます。`chip_id` で ESP32-S3、`flash_id` で 16 MB を確認します。異なる機種・容量、判定不能、Secure Boot やフラッシュ暗号化の影響が未確認の場合は停止します。出力は非公開で保管します。

   ```bash
   port='<選択した /dev/cu.usbmodem* のポート>'
   python -m esptool --port "$port" chip_id
   python -m esptool --chip esp32s3 --port "$port" flash_id
   python -m esptool --chip esp32s3 --port "$port" get_security_info
   ```

3. リポジトリ外に新規の非公開ディレクトリを作り、その場所を `backup_dir` に設定します。全 16 MiB を読み出します。16,777,216 バイトあることを確認し、チェックサムと対象端末の対応を非公開で保管します。

   ```bash
   umask 077
   backup_dir='<作成した非公開ディレクトリ>'
   backup="$backup_dir/factory-backup.bin"
   (
     set -e
     test ! -e "$backup"
     python -m esptool --chip esp32s3 --port "$port" read_flash 0 0x1000000 "$backup"
     test "$(wc -c < "$backup" | tr -d '[:space:]')" -eq 16777216
     cd "$backup_dir"
     shasum -a 256 factory-backup.bin > factory-backup.sha256
   )
   ```

4. 元のパーティション表をバックアップから解析し、GrokWatch の生成表と照合します。通常の ESP-IDF 配置でテーブルが `0x8000` にある場合は、下のコマンドで取り出せます。テーブルが読めない場合や、工場データの所在と書き込み範囲を確定できない場合は停止します。

   ```bash
   dd if="$backup" of="$backup_dir/original-partitions.bin" bs=4096 skip=8 count=1
   python "$IDF_PATH/components/partition_table/gen_esp32part.py" "$backup_dir/original-partitions.bin"
   python scripts/check_firmware_build.py
   ```

## 承認されたパーティションに書く

元のブートローダーが `0x10000` の factory アプリを起動でき、アプリの範囲が元の NVS・工場データに重ならないと確認できた場合のコマンドです。フラッシュを変更する前に、C152 向けの成果物、チェックサム、対象のオフセットと 4 KiB セクター単位の影響範囲を確認してください。テーブルやブートローダーの変更が必要な場合は、別途その範囲を確定し、承認を得るまで停止します。

```bash
python -m esptool --chip esp32s3 --port "$port" write_flash 0x10000 firmware/build/grokwatch.bin
```

NVS の書き込み・消去、全消去、保護機能の強制解除は禁止です。起動後は [仕様 §12](PHASE3_SPEC.md#12-実機でしか確かめられないことphase-5-用) に沿って確認し、[テスト報告](TEST_REPORT.md) に結果を記録します。[Espressif の esptool v4 コマンド仕様](https://docs.espressif.com/projects/esptool/en/release-v4/esp32s3/esptool/basic-commands.html)

## 元のフラッシュに戻す

稼働を止め、対象端末とバックアップの対応を確かめます。フラッシュ全体がバックアップ時点の状態に戻る影響を示し、復旧書き込みの承認を得てからダウンロードモードに入ります。

```bash
(
  set -e
  cd "$backup_dir"
  shasum -a 256 -c factory-backup.sha256
  python -m esptool --chip esp32s3 --port "$port" write_flash 0x0 factory-backup.bin
)
```

復旧後に元の起動とデータを確認します。バックアップと実機ログは非公開で保管します。
