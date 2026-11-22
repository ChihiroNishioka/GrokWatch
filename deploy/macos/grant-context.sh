#!/usr/bin/env bash
# 予定とメールを読む補助コマンドを、ターミナルから一度だけ動かす。
# macOS の許可ダイアログが出たら「許可」を押してください。結果は件数だけ表示します（内容は出しません）。
set -euo pipefail
umask 077

BIN="${GROKWATCH_CONTEXT_BIN:-$HOME/.local/share/GrokWatch/bin/grokwatch-context}"

cat <<'MSG'

=== GrokWatch に予定とメールの読み取りを許可します ===

これから Mac の画面に許可のダイアログが出ることがあります。
  ・「カレンダーへのフルアクセス」 → 「フルアクセスを許可」
  ・「メール.app の操作」        → 「OK」
※ メール.app は起動したままにしてください（このスクリプトは起動しません）。
※ 読むのは予定の件名と日時、メールの差出人・件名・受信日時だけです。メール本文は読みません。

MSG

if [[ ! -x $BIN ]]; then
	echo "!! 補助コマンドがありません。先に install.sh --bridge realtime を実行してください"
	exit 1
fi

count_of() {  # $1=JSON キー → 標準入力の JSON の件数
	python3 -c 'import json,sys; print(len(json.load(sys.stdin)[sys.argv[1]]))' "$1"
}

failed=0
today=$(date +%Y-%m-%d)
tomorrow=$(date -v+1d +%Y-%m-%d 2>/dev/null || date -d tomorrow +%Y-%m-%d)

echo "① カレンダーを確認します（今日と明日）…"
status=0
out=$("$BIN" schedule --from "$today" --to "$tomorrow" 2>/dev/null) || status=$?
case $status in
	0) echo "   OK: 今日と明日の予定は $(printf '%s' "$out" | count_of events) 件です" ;;
	3) echo "   !! 許可されていません。システム設定 > プライバシーとセキュリティ > カレンダー で grokwatch-context を許可してください"; failed=1 ;;
	*) echo "   !! 読み取りに失敗しました（コード $status）"; failed=1 ;;
esac

echo "② メールを確認します（直近 24 時間の未読）…"
status=0
out=$("$BIN" mail --since-hours 24 --limit 10 --unread-only 2>/dev/null) || status=$?
case $status in
	0) echo "   OK: 直近 24 時間の未読は（最大 10 件のうち）$(printf '%s' "$out" | count_of messages) 件です" ;;
	3) echo "   !! 許可されていません。システム設定 > プライバシーとセキュリティ > オートメーション で grokwatch-context のメールを許可してください"; failed=1 ;;
	4) echo "   !! メール.app が起動していません。メール.app を開いてからもう一度実行してください"; failed=1 ;;
	*) echo "   !! 読み取りに失敗しました（コード $status）"; failed=1 ;;
esac
unset out

echo
if ((failed)); then
	echo "=== 未完了の項目があります。上の指示に従ってから、もう一度このスクリプトを実行してください ==="
	exit 1
fi
echo "=== 完了。予定とメールの読み取りを許可できました ==="
