#!/usr/bin/env bash
# GrokWatch v1.2.0（OpenAI Realtime）に必要な鍵を設定する。
# 入れた値は画面に出さず、Keychain にだけ保存する。
set -euo pipefail
umask 077
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR

cat <<'MSG'

=== GrokWatch の高速な会話（OpenAI Realtime）を設定します ===

用意するもの
  1. OpenAI の API キー … sk- で始まる長い文字列（OpenAI の管理画面で作成したもの）
  2. 作業受付ルーチンの Webhook URL … https:// で始まる長い文字列（Grok Bot の「GrokWatch 作業受付」）
  3. 作業受付ルーチンの送信キー      … そのルーチンのパネルに出る秘密の文字列

※ Mac のログインパスワードや暗証番号ではありません。
※ 貼り付けても画面には何も表示されません（それで正常です）。貼り付けたら Enter。
※ 2 と 3 がまだなら、2 の欄で何も入れずに Enter を押すと飛ばせます（作業のお願いだけ使えなくなります）。

MSG

ask() {  # $1=見出し $2=空でもよいなら optional → 入力値を REPLY_VALUE に入れる
	local first second
	read -r -s -p "$1 を貼り付けて Enter: " first; echo
	if [[ ${2:-} == optional && -z $first ]]; then
		REPLY_VALUE=''
		return 0
	fi
	read -r -s -p "確認のため、もう一度 $1 を貼り付けて Enter: " second; echo
	[[ $first == "$second" ]] || { echo "!! 1回目と2回目が違います。何も保存していません。最初からやり直してください"; exit 1; }
	first="${first#"${first%%[![:space:]]*}"}"; first="${first%"${first##*[![:space:]]}"}"
	REPLY_VALUE=$first
}

ask "① OpenAI の API キー"
openai=$REPLY_VALUE
if [[ $openai == http* ]]; then
	echo "!! API キーの欄に URL が入っています。何も保存していません"; exit 1
fi
if [[ $openai != sk-* ]] || (( ${#openai} < 20 )); then
	echo "!! OpenAI の API キーではないようです（sk- で始まる長い文字列が必要です）。何も保存していません"
	exit 1
fi

ask "② 作業受付の Webhook URL" optional
url=$REPLY_VALUE
key=''
if [[ -n $url ]]; then
	if [[ ! $url =~ ^https://[^/[:space:]]+\.[^/[:space:]]+(/[^[:space:]]*)?$ ]] || (( ${#url} < 20 )); then
		echo "!! URL ではないようです（https:// で始まる長い文字列が必要です）。何も保存していません"
		exit 1
	fi
	ask "③ 作業受付の送信キー"
	key=$REPLY_VALUE
	if [[ $key == http* ]]; then
		echo "!! 送信キーの欄に URL が入っています。何も保存していません"; exit 1
	fi
	if (( ${#key} < 16 )); then
		echo "!! 送信キーが短すぎます（${#key} 文字）。パネルの送信キーを丸ごとコピーしてください。何も保存していません"; exit 1
	fi
	[[ $key != "$url" && $key != "$openai" ]] || { echo "!! 同じ値が重複しています。何も保存していません"; exit 1; }
fi

tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
save() {
	printf '%s' "$2" > "$tmp"; chmod 600 "$tmp"
	bash "$SCRIPT_DIR/keychain-add.sh" --file "$tmp" "$1" >/dev/null
	: > "$tmp"
}
save GROKWATCH_OPENAI_API_KEY "$openai"
if [[ -n $url ]]; then
	save GROKWATCH_TASK_WEBHOOK_URL "$url"
	save GROKWATCH_TASK_WEBHOOK_KEY "$key"
	host=$(python3 -c 'import sys,urllib.parse as u; print(u.urlsplit(sys.argv[1]).hostname)' "$url")
fi
unset openai url key REPLY_VALUE

echo "保存しました（OpenAI の API キー: 保存済み）"
if [[ -n ${host:-} ]]; then
	echo "保存しました（作業受付の宛先: $host / 送信キー: 保存済み）"
else
	echo "作業受付は設定していません（あとで、このスクリプトをもう一度実行すれば追加できます）"
fi

cat <<'MSG'

=== 完了 ===
次に、次のコマンドを実行してください（予定とメールの許可を出します）:
  bash deploy/macos/grant-context.sh
そのあと Gateway を切り替えます:
  bash deploy/macos/install.sh --bridge realtime \
    --whisper-model "$HOME/.local/share/GrokWatch/models/ggml-base.bin"
MSG
