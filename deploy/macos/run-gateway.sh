#!/usr/bin/env bash
set -euo pipefail

readonly GW_UV_VERSION=0.13.9
GW_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly GW_REPO
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [[ -n ${GROKWATCH_BRIDGE_OVERRIDE:-} ]]; then
	case $GROKWATCH_BRIDGE_OVERRIDE in
		mock|webhook) export GROKWATCH_BRIDGE="$GROKWATCH_BRIDGE_OVERRIDE" ;;
		*) printf '%s\n' 'GROKWATCH_BRIDGE_OVERRIDE must be mock or webhook' >&2; exit 64 ;;
	esac
fi

unset GROKWATCH_DEVICE_TOKEN GROKWATCH_WEBHOOK_URL GROKWATCH_WEBHOOK_KEY GROKWATCH_ALLOW_ENV_SECRETS

if ! command -v uv >/dev/null 2>&1; then
	printf '%s\n' 'uv is not installed or is not on PATH' >&2
	exit 69
fi
uv_version=$(uv --version)
if [[ $uv_version != "uv $GW_UV_VERSION "* ]]; then
	printf 'Expected uv %s\n' "$GW_UV_VERSION" >&2
	exit 69
fi

exec uv run --locked --project "$GW_REPO/gateway" --python 3.11 python -m grokwatch_gateway
