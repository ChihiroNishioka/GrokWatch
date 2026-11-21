#!/usr/bin/env bash
set -euo pipefail

readonly LABEL='com.grokwatch.gateway'
DRY_RUN=0
while (($#)); do
	case $1 in
		--dry-run) DRY_RUN=1; shift ;;
		-h|--help) printf '%s\n' 'Usage: uninstall.sh [--dry-run]'; exit 0 ;;
		*) printf '%s\n' 'Usage: uninstall.sh [--dry-run]' >&2; exit 64 ;;
	esac
done

gui_domain="gui/$(id -u)"
target="$gui_domain/$LABEL"
plist_path="${HOME:?HOME is required}/Library/LaunchAgents/$LABEL.plist"
if ((DRY_RUN)); then
	printf 'Would remove the LaunchAgent and plist: %s\n' "$LABEL"
	exit 0
fi

if launchctl print "$target" >/dev/null 2>&1; then
	launchctl bootout "$target"
fi
rm -f -- "$plist_path"
printf 'LaunchAgent %s を削除しました。ログと Keychain 項目は残しました。Serve を設定した場合は、次のコマンドで返信口を解除してください。\n' "$LABEL"
printf '%s\n' 'tailscale serve --https=443 --set-path=/v1/reply off'
