#!/usr/bin/env bash
set -euo pipefail

GW_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly GW_REPO
GW_PYTHON="$GW_REPO/.venv/bin/python"
readonly GW_PYTHON
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [[ -n ${GROKWATCH_BRIDGE_OVERRIDE:-} ]]; then
	case $GROKWATCH_BRIDGE_OVERRIDE in
		mock|webhook|realtime) export GROKWATCH_BRIDGE="$GROKWATCH_BRIDGE_OVERRIDE" ;;
		*) printf '%s\n' 'GROKWATCH_BRIDGE_OVERRIDE must be mock, webhook or realtime' >&2; exit 64 ;;
	esac
fi

unset GROKWATCH_DEVICE_TOKEN GROKWATCH_WEBHOOK_URL GROKWATCH_WEBHOOK_KEY GROKWATCH_OPENAI_API_KEY \
	GROKWATCH_TASK_WEBHOOK_URL GROKWATCH_TASK_WEBHOOK_KEY GROKWATCH_ALLOW_ENV_SECRETS

if [[ ! -x $GW_PYTHON ]]; then
	printf '%s\n' 'Gateway virtual environment is missing; run install.sh first' >&2
	exit 69
fi
python_version=$("$GW_PYTHON" --version 2>&1)
if [[ $python_version != 'Python 3.11.'* ]]; then
	printf '%s\n' 'Expected the Gateway virtual environment to use Python 3.11' >&2
	exit 69
fi

exec "$GW_PYTHON" -m grokwatch_gateway
