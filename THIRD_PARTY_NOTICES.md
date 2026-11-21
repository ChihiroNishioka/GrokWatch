# 第三者ライセンスと再配布条件

現時点で第三者コードや素材は取り込んでいません。以下は参照先と将来の候補です。Phase 3 で採用する版とファイルを確定し、依存物を含む配布条件を再確認します。

| 参照対象 | ライセンス・再配布条件 |
| --- | --- |
| groki-bot ファームウェア | Boost Software License 1.0（BSL-1.0）。ソースや派生ソースを配布する場合は、元の著作権表記とライセンス文を全文保持します。将来取り込む BSL-1.0 由来のファイルには、引き続き BSL-1.0 が適用されます。ライセンスには機械実行可能なオブジェクトコードのみの配布に関する例外があります。 |
| groki-bot gateway | MIT。コピーまたは主要部分の再配布時に `gateway/LICENSE` の全著作権表記と許諾文を保持します。著作権表記は Shenzhen Xinzhi Future Technology Co., Ltd.、Project Contributors、kisaragi-mochi、Groki Bot contributors です。SCServo_lib（GPL-3.0）に関する同ファイルの注記は上流ファームウェアの話です。Groki Bot の通知文では、同ライブラリは Groki Bot ファームウェアには含まれません。 [上流の gateway ライセンス](https://github.com/JosssphZhou/groki-bot/blob/699a370493e30b196cc7f73f712322cc55c28ec2/gateway/LICENSE) |
| Emotion Ball の目リングと表情データ | Emotion Ball Community License。商用利用は別途許可が必要です。当該データを含む配布ファームにも非商用条件が及びます。配布済みの groki-bot ファームにはこのデータが含まれます。GrokWatch には取り込みません。 |
| HTS Voice「Mei」 | CC BY 3.0。再配布時に Nagoya Institute of Technology / MMDAgent Project Team の帰属、出典、ライセンスを表示します。改変版では変更内容も明示します。 |
| hts_engine API | BSD-3-Clause。ソース配布では著作権表示、条件、免責を残し、バイナリ配布では添付文書等に再掲します。権利者名を無断で推奨や宣伝に用いません。 |
| esp-sr | Espressif 製品での使用に限定された MIT 系ライセンス。音声モデルを含め、対象製品の制限と著作権・許諾表示を引き継ぎます。 |
| esp_audio_codec | Espressif 製品での使用に限定された Espressif Modified MIT License。対象製品の制限と著作権・許諾表示を引き継ぎます。 |
| grok-command-watch | MIT。著作権表示・許諾文を保持し、再配布には `LICENSE` と `NOTICE.md`・`NOTICE.en.md` を同梱します。 |
| codex-micro-stopwatch | MIT。C152 初期化の上流候補です。コピーまたは主要部分の再配布時に元の著作権表示と許諾文を保持します。 |
| openai-live-esp32 | Apache-2.0。再配布時はライセンスを同梱し、該当する `NOTICE` の帰属表示を保持します。派生ソースの配布時は、該当する著作権・特許・商標・帰属の表示を保持します。変更したファイルには変更を明示します。libpeer（MIT）やフォントなどは個別の通知と条件を確認します。 |
| whisper.cpp | MIT。再配布時に著作権表示と許諾文を保持します。採用するモデルの配布条件は別途確認します。 [上流のライセンス](https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE) |
| sherpa-onnx | Apache-2.0。ライセンスと該当する NOTICE・帰属表示を保持します。groki-bot が参照するキーワード検出モデルは約 33 MB。モデルの配布条件は採用時に確認します。 [上流のライセンス](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE) |
| grok-bot-cli | MIT。再配布時は著作権表示と許諾文を保持します。利用者が必要に応じて導入する外部ツールで、GrokWatch は同梱しません。 |
| M5Unified | MIT。再配布時は著作権表示と許諾文を保持し、取り込む依存物の通知も確認します。 |
| M5GFX | MIT。再配布時は著作権表示と許諾文を保持します。内蔵フォントは個別のライセンスを確認します。GrokWatch のビルドは、M5GFX 0.2.30 の `src/M5GFX.cpp` からボード判定の NVS キャッシュ処理を外した複製をビルドディレクトリに生成して使います（`firmware/CMakeLists.txt`）。リポジトリには M5GFX のソースを含めません。ファームのバイナリを配布する場合は M5GFX の著作権表示と許諾文を同梱します。 |
| X の参照動画 | URL と文章による観察記録を参照します。動画、スクリーンショット、キャラクター素材、音声は使いません。 |
| M5Burner の配布素材 | ファームウェアや素材の配布条件は作者ごとに異なります。再配布許諾を確認できていない素材は使いません。 |

## groki-bot ファームウェアの著作権表記

```text
Copyright (c) 2026 Kenta IDA
Copyright (c) 2026 Joseph Zhou
```

条件の確認先は [groki-bot のライセンス](https://github.com/JosssphZhou/groki-bot/blob/699a370493e30b196cc7f73f712322cc55c28ec2/LICENSE) と [依存物の通知](https://github.com/JosssphZhou/groki-bot/blob/699a370493e30b196cc7f73f712322cc55c28ec2/THIRD_PARTY_NOTICES.md) を参照してください。
