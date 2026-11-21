#!/usr/bin/env bash
set -euo pipefail

readonly LABEL='com.grokwatch.gateway'
if (($#)); then
	if [[ $1 != --dry-run || $# != 1 ]]; then
		printf '%s\n' 'Usage: status.sh [--dry-run]' >&2
		exit 64
	fi
fi

gui_domain="gui/$(id -u)"
target="$gui_domain/$LABEL"
printf '%s\n' "LaunchAgent $LABEL:"
if launchctl print "$target"; then :; else printf '%s\n' 'not loaded'; fi

for port in 8765 8767; do
	if lsof -nP -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
		printf 'Port %s: listening\n' "$port"
	else
		printf 'Port %s: free\n' "$port"
	fi
done

if command -v curl >/dev/null 2>&1 && curl --silent --show-error --max-time 2 \
	-o /dev/null -w '%{http_code}' http://127.0.0.1:8767/healthz 2>/dev/null | grep -qx 200; then
	printf '%s\n' 'Health: 200'
else
	printf '%s\n' 'Health: unavailable'
fi

for account in GROKWATCH_DEVICE_TOKEN GROKWATCH_WEBHOOK_URL GROKWATCH_WEBHOOK_KEY; do
	if security find-generic-password -s grokwatch -a "$account" >/dev/null 2>&1; then
		printf 'Keychain %s: present\n' "$account"
	else
		printf 'Keychain %s: missing\n' "$account"
	fi
done

if command -v tailscale >/dev/null 2>&1; then
	printf '%s\n' 'Tailscale Serve:'
	tailscale serve status || true
else
	printf '%s\n' 'Tailscale Serve: unavailable'
fi
