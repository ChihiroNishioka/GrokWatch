# 進捗

2026-11-22 時点で v1.1.0 を実装しています。聞き取り中（マイク音量に反応するシアンのリング）と考え中（紫の回転弧・半目）の表示、返事の `emotion` に合わせた表情、「Hi Grok」ウェイクワード（Gateway 側判定、既定は無効）を追加しました。仕様は [v1.1.0 仕様](V1_1_SPEC.md)、結果は[テスト報告](TEST_REPORT.md)を参照してください。

Linux 上の host test、pytest、ファームウェアのクリーンビルドは通過しています。StopWatch C152 での表示・音声・ウェイクワードは未確認です。Mac mini への Gateway 更新と StopWatch への書き込みは、対象と影響を示して承認を得てから行います。導入手順は[セットアップガイド](SETUP.md)に記載しています。

## v1.2.0（2026-11-22）

Mac 側と文書を準備しました。予定・メールを読む Swift 補助コマンド `grokwatch-context`（`tools/grokwatch-context/`）、`install.sh --bridge realtime`（補助コマンドのビルド、Keychain 確認）、鍵の案内付き登録 `set-realtime-keys.sh`、許可の取得 `grant-context.sh`、作業受付ルーチンの指示文（[webhook ブリッジ仕様](BRIDGE_WEBHOOK.md)）です。版番号は firmware・gateway・bridge とも 1.2.0 です。

Linux ではシェルと文書のテストだけを実行しました。Swift の補助コマンドはこの開発機にコンパイラがなく、ビルドも動作も未確認です。Mac mini でのビルド、許可ダイアログ、メール.app の動作、StopWatch での遅延と声は未確認で、承認を得てから確かめます。
