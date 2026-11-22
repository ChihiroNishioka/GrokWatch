# v1.2.0 仕様案（OpenAI Realtime で速く答える）

状態: 実装中（ビルドとモックのみ、実機未検証）。前提は [v1.1.0 仕様](V1_1_SPEC.md) と [Phase 3〜4 仕様](PHASE3_SPEC.md)。ここに書かない動作は変えない。版番号は firmware・gateway・bridge とも `1.2.0`。

## 1. オーナー要望と方針

| 要望 | 方針 |
| --- | --- |
| 返事が遅い（Grok Bot のコンピューターを毎回起こすため） | 会話は OpenAI Realtime API（音声→音声）で行い、Grok Bot を待たない |
| 予定・メールの文脈は持っていてほしい | Mac mini の「カレンダー」「メール」アプリから Gateway が直接読む |
| 作業の依頼は「やっておく」と返せばよい | Grok Bot の作業用ルーチンに投げて、音声では受付だけ返す |
| 頼める作業は限定しない | 何でも受ける。ただし送信・削除・購入など取り返しのつかない操作は音声からは受けない |

既存の webhook 経路（v1.1.0）は残し、`GROKWATCH_BRIDGE=realtime` で切り替える。ファームウェアの変更は不要（版番号のみ）。

## 2. 流れ

```
StopWatch ─PCM16 16kHz─▶ Gateway ─(変換)─▶ OpenAI Realtime ─音声─▶ Gateway ─▶ StopWatch
                            ▲          必要なときだけ関数を呼ぶ           │
                            └──────────────────────────────────────────┘
```

1. `listen_start`: Realtime セッションが無ければ開く（WebSocket、サーバー側からのみ。API キーは Keychain）。会話の文脈を残すため、最後の発話から 5 分はセッションを保持する。
2. 収音フレーム: 16 kHz → 24 kHz に変換して `input_audio_buffer.append`。Gateway は同じ PCM を手元にも保持する（§6 のフォールバック用）。
3. `listen_stop`: 自動の発話検出は使わず（`turn_detection: none`）、`input_audio_buffer.commit` と `response.create` を即送る。長押しを離した瞬間が話し終わり。
4. 返事の音声 `response.output_audio.delta`（24 kHz）を 16 kHz に変換し、既存の `tts_start` → バイナリ → `tts_end` で端末へ流す。最初の音声が届くまで端末は Thinking。
5. 関数呼び出しが来たら Gateway が実行し、結果を返して `response.create` で続きを話させる。実行中は Thinking。

GPT-Live セッション（16 kHz を直接扱え、Web 検索の委譲がある）も実装時に試し、遅延の小さい方を既定にする。

## 3. 関数（Gateway が実行する道具）

| 名前 | 引数 | 動作 | 返事の目安 |
| --- | --- | --- | --- |
| `get_schedule` | `from`, `to`（日付。省略時は今日〜明日） | カレンダー.app の予定（件名・開始/終了・場所・終日）を最大 30 件 | 即答 |
| `get_mail` | `unread_only`（既定 true）、`since_hours`（既定 24）、`limit`（既定 10） | メール.app の受信箱の差出人・件名・受信日時。本文は読まない | 即答 |
| `web_search` | `query` | OpenAI Responses API の `web_search` で調べ、短い日本語の要約を返す | 数秒 |
| `delegate_to_grok_bot` | `request`（依頼文） | Grok Bot の作業用ルーチンへ webhook で送るだけ（返事を待たない） | 「やっておくね」 |

- 指示文（system）で、送信・削除・購入・支払い・予約の確定は `delegate_to_grok_bot` に渡さず「それはチャットで頼んでね」と答えるよう定める。作業用ルーチン側の指示文にも同じ禁止を書く（二重の歯止め）。
- 予定・メールの結果は会話に使うだけで、Gateway は保存もログ出力もしない（ログは件数と所要時間のみ）。

## 4. 予定とメールの読み取り（Mac mini）

| 対象 | 方法 | 権限 |
| --- | --- | --- |
| カレンダー | Swift の小さな補助コマンド `grokwatch-context`（EventKit）。Gateway が呼ぶ | 初回に「カレンダーへのフルアクセス」の許可ダイアログ |
| メール | 同じ補助コマンドから AppleScript でメール.app を読む（受信箱、未読、期間指定） | 初回に「メールの操作」の許可ダイアログ。メール.app が起動している必要あり |

- 補助コマンドは `deploy/macos/install.sh` でビルド・配置する。許可ダイアログはオーナーが Mac mini の前で一度承認する。
- 応答を速くするため、Gateway は結果を 5 分キャッシュし、`listen_start` のときに裏で更新を始める。

## 5. 作業用ルーチン（Grok Bot 側）

- 既存の返事用ルーチンとは別に、webhook トリガーの「GrokWatch 作業受付」を作る。URL と送信キーは Keychain の `GROKWATCH_TASK_WEBHOOK_URL` / `GROKWATCH_TASK_WEBHOOK_KEY`。
- payload: `{"v":1,"type":"task","request_id","text","created_at"}`。返信口への返事は不要。結果はオーナーの Grok Bot チャットに通知する。
- 指示文に、送信・削除・購入などの取り返しのつかない操作は実行せず、チャットで確認を求めることを書く。

## 6. 失敗時

| 場面 | 動作 |
| --- | --- |
| Realtime に接続できない・途中で切れた | その発話は手元の PCM で従来経路（whisper → webhook）に回す。それも失敗したら定型音声 |
| 関数がタイムアウト（予定・メール 3 秒、検索 10 秒） | 「いま確認できなかった」と答えさせる |
| 作業用ルーチンへの送信失敗 | 「頼めなかったから、あとでチャットで送ってね」と答えさせる |

## 7. 設定

| 変数 / Keychain | 既定 | 説明 |
| --- | --- | --- |
| `GROKWATCH_BRIDGE` | `webhook` | `realtime` で本仕様 |
| Keychain `GROKWATCH_OPENAI_API_KEY` | — | 必須（realtime 時） |
| `GROKWATCH_REALTIME_MODEL` | `gpt-realtime-2.1` | 実装時に最新を確認 |
| `GROKWATCH_REALTIME_VOICE` | `marin` | 返事の声 |
| `GROKWATCH_SEARCH_MODEL` | `gpt-6.2-astra` | `web_search` 用の Responses モデル |
| Keychain `GROKWATCH_TASK_WEBHOOK_URL` / `_KEY` | — | 作業用ルーチン |

Keychain への登録は `grokwatch-tools/set-webhook.sh` と同じ形式の案内付きスクリプトで行う。

## 8. 範囲外（今回は実装しない）

- 返事に合わせた表情（emotion）。Realtime 経路では neutral のまま（関数呼び出し中は Thinking）。次版で検討
- 返事の途中で話しかけて割り込むこと
- メール本文の読み上げ

## 9. 実機で確かめること

- 話し終わりから返事の声が出るまでの時間（目標 1.5 秒以内）と、関数を使う場合の時間
- OpenAI の声の聞き取りやすさ（StopWatch のスピーカー）
- カレンダー・メールの許可が LaunchAgent から有効か、メール.app が起動していないときの動作
- 1 回の会話あたりの料金
