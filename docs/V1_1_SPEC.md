# v1.1.0 仕様（聞き取り・考え中の表示、表情、ウェイクワード）

状態: 実装中（ビルドとモックのみ、実機未検証）。数値は Phase 5 の実機確認で見直す。
前提は [Phase 3〜4 仕様](PHASE3_SPEC.md)。ここに書かない動作は変えない。版番号は firmware・gateway・bridge とも `1.1.0`（プロトタイプはタグ `v1.0.0`。そのコード内の版表記は 0.1.0 のままだった）。

## 1. オーナー要望

| 要望 | 対応 |
| --- | --- |
| 聞き取り中と考え中が Idle と見分けられない | §2。Listening はマイク音量に反応する色付きリング、Thinking は回転する弧 |
| 感情で表情を変える | §3。webhook 返信の `emotion` を `tts_start` で端末へ送る |
| 「Hi Grok」で話しかけたい | §4。端末は Idle 中の発話区間だけ gateway へ送り、gateway の whisper.cpp で照合する。既定は無効 |

## 2. Listening と Thinking の表示

`makeFace(state, gaze, blink, level, elapsed, shape)` の変更。リング半径はすべて 214（音量による縮小は従来どおり `scaleFace` で掛ける）。

### 2.1 Listening

| 項目 | 値 |
| --- | --- |
| リング | 実線、色 `#22C7FF`（シアン） |
| リング太さ | `6 + 3 × breath + 12 × level`。`breath = 0.5 − 0.5 cos(2π × elapsed / 1200 ms)`、`level` はマイク音量（§2.3）。最大 21 px |
| 目の高さ倍率 | 入った直後の「耳を立てる」動き: 0〜120 ms で 1.00→1.25 に線形、120〜300 ms で 1.25→1.15 に線形、以後 1.15 |
| 視線 | 中央（従来どおり。ドラッグ・タップは従う） |
| 瞬き | 自発瞬きなし（従来どおり） |

### 2.2 Thinking

| 項目 | 値 |
| --- | --- |
| リング | 新しい種類 `RingKind::Arc`。色 `#B07CFF`（紫）、太さ 8、弧の長さ `sweep = 100°`、開始角 `start = 360 × (elapsed mod 1000) / 1000`（度。M5GFX の `fillArc` と同じく 3 時方向が 0°、時計回り） |
| 視線 | `g_x = 0.4 × sin(2π t / 2.4 s)`、`g_y = −0.3`（上を見ながら左右に考える） |
| まぶた | 上まぶたを水平に `0.22`（目の高さに対する割合）下ろす |
| 20 秒の合図 | 従来どおり 3 点を足す |

### 2.3 マイク音量

`level_mic = clamp((RMS − 400) / 2600, 0, 1)`。平滑は既存 `AudioLevel` と同じ（立ち上がり 30 ms、減衰 120 ms、100 ms 途切れたら 200 ms で 0）。`AudioLevel::frameRaw(now, raw)` を足し、既存の `frame(now, rms)` は `frameRaw(now, rawLevel(rms))` を呼ぶ。端末は再生用 `app.level` とは別の `app.micLevel` を持ち、収音フレームごとに更新する。描画は Listening のとき `micLevel`、それ以外は `level` を渡す。

### 2.4 目の安全域

表情や倍率で大きくなった目は、外接矩形の角が中心から 196 px を超えないよう、幅と高さを同じ比で縮める（`fitInside`）。

## 3. 表情（emotion）

### 3.1 経路

1. webhook 返信の `emotion`（`neutral` `happy` `sad` `surprised` `thinking`。未知・省略は `neutral`）を gateway が受ける（既存）。
2. gateway は `tts_start` に任意フィールド `emotion`（文字列）を付ける。返事の再生では返信の値、定型音声（エラー時）では `sad`。
3. 端末は `tts_start` の `emotion` で表情を設定する。フィールドがない・未知なら `neutral`。旧端末は余分なフィールドを無視するので互換。

### 3.2 形（オリジナル。Emotion Ball 等のデータは使わない）

`ExpressionShape { width, height, lidInner, lidOuter, lidBottom, gazeY }`。`width`・`height` は目の倍率、`lid*` は目の高さに対する割合、`gazeY` は視線の y に足す値。

| emotion | width | height | lidInner | lidOuter | lidBottom | gazeY | 見た目 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| neutral | 1 | 1 | 0 | 0 | 0 | 0 | 通常 |
| happy | 1.05 | 1 | 0 | 0 | 0.55 | −0.10 | 下から白い弧で隠し「^ ^」 |
| sad | 1 | 0.9 | 0 | 0.40 | 0 | 0.25 | 外側が下がる上まぶた、視線やや下 |
| surprised | 1.2 | 1.2 | 0 | 0 | 0 | −0.05 | 目を見開く |
| thinking | 1 | 1 | 0.22 | 0.22 | 0 | −0.30 | 半目で上を見る |

まぶたの描き方（描画側）: 目のカプセルを黒で描いたあと、目の外接矩形にクリップして白で塗る。

- 上まぶた: 四角形 `(内側上端, 外側上端, 外側の y = top + h × lidOuter, 内側の y = top + h × lidInner)`。内側は顔の中心側（左目は右端、右目は左端）。
- 下まぶた（`lidBottom > 0`）: 白い楕円。半径 `rx = 1.2 w`、`ry = 0.9 h`、中心 `y = bottom − h × lidBottom + ry`、中心 `x` は目と同じ。

core は `Eye` に `lidInner`・`lidOuter`・`lidBottom` を持たせ、`scaleFace` はこれらをそのまま写す（割合なので倍率不要）。

### 3.3 時間

| 場面 | 動き |
| --- | --- |
| `tts_start` で設定 | 現在の形から 200 ms で目標の形へ線形補間 |
| Speaking から別状態へ | 1,200 ms 保持してから 300 ms で neutral へ |
| Listening・Thinking・Disconnected に入る | 150 ms で neutral へ |
| Thinking 中 | 状態のまぶた 0.22 と表情の lid の大きい方 |

## 4. 「Hi Grok」ウェイクワード

### 4.1 方式

ESP-SR には「Hi Grok」の既製モデルがないため、gateway 側で判定する。端末は Idle 中も収音し、発話の区間（最大 2.5 秒）だけ送る。gateway は whisper.cpp で文字起こしし、ウェイク句と照合する。音声と文字起こしは保存しない。

### 4.2 有効化

- gateway: `GROKWATCH_WAKE=1` で有効（既定 `0`）。`hello_ok` に `"wake": true` を付ける。無効なら付けない。
- 端末: Kconfig `CONFIG_GROKWATCH_WAKE_WORD`（bool、既定 y）かつ `hello_ok.wake == true` のときだけ Idle 中に収音する。
- 任意の `GROKWATCH_WAKE_MODEL`（whisper モデルのパス）。省略時は `GROKWATCH_WHISPER_MODEL`。STT が mock のときは mock の固定文で照合する（テスト用）。

### 4.3 端末の区間切り出し（core `WakeSegmenter`）

| 項目 | 値 |
| --- | --- |
| プリロール | 直近 15 フレーム（300 ms）を常に保持 |
| 開始 | RMS 700 以上が連続 3 フレーム |
| 終了 | 開始後、RMS 500 未満が連続 25 フレーム（500 ms）、またはプリロール込みで 125 フレーム（2.5 秒） |
| 判定待ち | 終了後は gateway の `wake` を最大 4,000 ms 待つ。待つ間は新しい区間を始めない（プリロールは更新し続ける） |
| 取消 | Idle を離れたら区間と判定待ちを捨てる（gateway へは何も送らない。gateway は `listen_start` で破棄する） |

`frame(pcm, rms, now)` は `None` / `Start` / `Send` / `Stop` を返す。`Start` のとき呼び出し側は `wake_start{seq}` を送り、プリロール（今のフレームを含む）を古い順に送る。`Send` は今のフレームを送る。`Stop` は今のフレームを送ってから `wake_stop{seq}` を送る。`seq` は区間ごとに 1 から増える正の整数。

### 4.4 端末の状態機械

`AvatarStateMachine::wake(now)`: Idle のときだけ長押しと同じく Listening に入り `listen_start` を送る。それ以外は何もしない。`wake{seq, hit:true}` を受け、`seq` が判定待ちと一致したときに呼ぶ。`hit:false` は判定待ちを解くだけ。Idle 中の収音では Listening の表示（リング・音量）を出さない。

### 4.5 プロトコル（v1 への追加。`v` は 1 のまま）

| type | 方向 | フィールド | 説明 |
| --- | --- | --- | --- |
| `hello_ok` | gw → 端末 | 任意 `wake`(bool) | true ならウェイクワード対応 |
| `wake_start` | 端末 → gw | `seq`(正の整数) | 以後のバイナリはウェイク判定用 |
| `wake_stop` | 端末 → gw | `seq` | 区間の終わり。gw は判定して `wake` を返す |
| `wake` | gw → 端末 | `seq`(正の整数)、`hit`(bool) | 判定結果 |
| `tts_start` | gw → 端末 | 任意 `emotion`(str) | §3 |

- gateway はウェイクが無効なら `wake_start`・`wake_stop` を未知の type と同じく無視し、そのバイナリも捨てる。
- 判定中に新しい `wake_start` が来たら古い判定を取り消す（結果も送らない）。`listen_start` が来たら区間と判定を捨てる。
- 区間の上限は 125 フレーム。超えたフレームは捨てる。15 フレーム未満の区間は STT にかけず `hit:false`。
- 会話処理中（`task` 実行中）に来た区間は判定せず `hit:false`。

### 4.6 照合（gateway）

文字起こしを NFKC → 小文字 → ひらがなをカタカナ → 空白・句読点・記号・長音以外の区切りを除去して正規化し、次の正規表現を探す。

```
(ハイ|ヘイ|ハーイ|ネエ|ネー|ねえ|HI|HEY|OK|オーケー)(グロック|グロク|グロッグ|グロッ?ク|GROK|GROCK|GROQ|GROC)
```

`GROKWATCH_WAKE_PATTERN` で正規表現を上書きできる。ログは `wake_check`（`hit`、`latency_ms`、`frames`）だけ。本文は `GROKWATCH_LOG_TEXT=1` のときだけ伏字処理後に出す。

### 4.7 範囲外（今回は実装しない）

- 「Hi Grok、明日の天気は？」を一息で言ったときに後半を発話として使うこと（ウェイク後に改めて聞く）
- 端末内でのウェイクワード検出、確認音

## 5. 実機でしか確かめられないこと

- リングの色と太さが小さい顔（既定音量）でも目立つか。マイク音量の係数（400 / 2600）が声に合うか
- 表情のまぶた形が意図どおりに見えるか、30 fps を保てるか
- Idle 中の常時収音による電池持ちと発熱、誤検出の頻度、判定の遅延（目標 1.5 秒以内）
- Idle 収音から Listening への切り替えでマイクの再起動が遅れないか
