#!/usr/bin/env bash
set -euo pipefail

readonly LABEL='com.grokwatch.gateway'
readonly UV_VERSION='0.13.9'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
BRIDGE='webhook'
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
WHISPER_MODEL=''
DRY_RUN=0

usage() {
	printf '%s\n' 'Usage: install.sh [--bridge mock|webhook] [--repo PATH] [--whisper-model PATH] [--dry-run]'
}

while (($#)); do
	case $1 in
		--bridge)
			(($# >= 2)) || { usage >&2; exit 64; }
			BRIDGE=$2
			shift 2
			;;
		--repo)
			(($# >= 2)) || { usage >&2; exit 64; }
			REPO_DIR=$2
			shift 2
			;;
		--whisper-model)
			(($# >= 2)) || { usage >&2; exit 64; }
			WHISPER_MODEL=$2
			shift 2
			;;
		--dry-run)
			DRY_RUN=1
			shift
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			usage >&2
			exit 64
			;;
	esac
done

case $BRIDGE in
	mock|webhook) ;;
	*) printf '%s\n' 'Bridge must be mock or webhook' >&2; exit 64 ;;
esac

REPO_DIR="$(cd -- "$REPO_DIR" && pwd -P)"
HOME_DIR="$(cd -- "${HOME:?HOME is required}" && pwd -P)"
if [[ -z $WHISPER_MODEL ]]; then
	WHISPER_MODEL="$REPO_DIR/models/ggml-base.bin"
fi
if [[ $WHISPER_MODEL != /* ]]; then
	WHISPER_MODEL="$REPO_DIR/$WHISPER_MODEL"
fi
[[ -r $WHISPER_MODEL ]] || { printf '%s\n' 'Whisper model is missing or unreadable' >&2; exit 66; }

for command in launchctl lsof security uv python3; do
	command -v "$command" >/dev/null 2>&1 || { printf 'Required command is missing: %s\n' "$command" >&2; exit 69; }
done
uv_version=$(uv --version 2>/dev/null) || { printf '%s\n' 'Could not read the uv version' >&2; exit 69; }
[[ $uv_version == "uv $UV_VERSION "* ]] || { printf 'Expected uv %s\n' "$UV_VERSION" >&2; exit 69; }

missing=()
security find-generic-password -s grokwatch -a GROKWATCH_DEVICE_TOKEN >/dev/null 2>&1 || \
	missing+=(GROKWATCH_DEVICE_TOKEN)
if [[ $BRIDGE == webhook ]]; then
	for account in GROKWATCH_WEBHOOK_URL GROKWATCH_WEBHOOK_KEY; do
		security find-generic-password -s grokwatch -a "$account" >/dev/null 2>&1 || missing+=("$account")
	done
fi
if ((${#missing[@]})); then
	printf 'Missing Keychain item: %s\n' "${missing[@]}" >&2
	exit 78
fi

gui_domain="gui/$(id -u)"
target="$gui_domain/$LABEL"
job_info=''
job_loaded=0
if job_info=$(launchctl print "$target" 2>/dev/null); then
	job_loaded=1
fi
job_pid=$(printf '%s\n' "$job_info" | sed -n 's/^[[:space:]]*pid = \([0-9][0-9]*\)$/\1/p' | head -n 1)
for port in 8765 8767; do
	listeners=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
	for pid in $listeners; do
		if [[ -z $job_pid || $pid != "$job_pid" ]]; then
			printf 'Port %s is already in use\n' "$port" >&2
			exit 73
		fi
	done
done

launch_agents="$HOME_DIR/Library/LaunchAgents"
plist_path="$launch_agents/$LABEL.plist"
logs="$HOME_DIR/Library/Logs/GrokWatch"
temporary=$(mktemp "${TMPDIR:-/tmp}/$LABEL.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
python3 - "$SCRIPT_DIR/com.grokwatch.gateway.plist.template" "$temporary" \
	"$HOME_DIR" "$REPO_DIR" "$BRIDGE" "$WHISPER_MODEL" <<'PY'
from pathlib import Path
import sys
from xml.sax.saxutils import escape

source, target, home, repo, bridge, model = sys.argv[1:]
replacements = {
    "@HOME@": escape(home),
    "@REPO@": escape(repo),
    "@BRIDGE@": escape(bridge),
    "@WHISPER_MODEL@": escape(model),
}
text = Path(source).read_text(encoding="utf-8")
for key, value in replacements.items():
    text = text.replace(key, value)
if any(key in text for key in replacements):
    raise SystemExit("Unexpanded plist placeholder")
Path(target).write_text(text, encoding="utf-8")
PY

if [[ -f $plist_path ]] && cmp -s "$temporary" "$plist_path"; then
	if ((job_loaded)); then
		printf 'Already installed: %s\n' "$LABEL"
		exit 0
	fi
	if ((DRY_RUN)); then
		printf 'Would load existing plist: %s\n' "$LABEL"
		exit 0
	fi
	launchctl bootstrap "$gui_domain" "$plist_path"
	printf 'Loaded: %s\n' "$LABEL"
	exit 0
fi

if ((DRY_RUN)); then
	if ((job_loaded)); then
		printf 'Would replace and reload: %s\n' "$LABEL"
	else
		printf 'Would install and load: %s\n' "$LABEL"
	fi
	exit 0
fi

mkdir -p "$launch_agents" "$logs"
chmod 700 "$logs"
if ((job_loaded)); then
	launchctl bootout "$target"
fi
install -m 600 "$temporary" "$plist_path"
launchctl bootstrap "$gui_domain" "$plist_path"
printf 'Installed: %s\n' "$LABEL"
