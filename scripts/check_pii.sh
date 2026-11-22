#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

ipv4_octet='(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})'
private_ipv4="(^|[^0-9.])(10\.(${ipv4_octet}\.){2}|172\.(1[6-9]|2[0-9]|3[01])\.${ipv4_octet}\.|(192\.168|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7]))\.${ipv4_octet}\.)${ipv4_octet}($|[^0-9.]|\.($|[^0-9]))"
home_path='/(Users|home)/[^/[:cntrl:]<>"'"'"'`]+/|[/]workspace/'
uuid='(^|[^[:alnum:]_])[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}($|[^[:alnum:]_])'
jp_phone='(^|[^[:alnum:]_+])(0(120|570)[- ]?[0-9]{3}[- ]?[0-9]{3}|0[5789]0[- ]?[0-9]{4}[- ]?[0-9]{4}|0[1-9][0-9]{0,3}[- ][0-9]{1,4}[- ][0-9]{4}|0[1-9][0-9]{8}|\+81[- ]?(\(0\)[- ]?)?[1-9][0-9]{0,3}[- ]?[0-9]{1,4}[- ]?[0-9]{4})($|[^[:alnum:]_])'
email='[a-z0-9.!#$%&'"'"'*+/=?^_`{|}~-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}'
mac_address='(^|[^[:alnum:]_])([a-f0-9]{2}(:[a-f0-9]{2}){5}|[a-f0-9]{2}(-[a-f0-9]{2}){5}|[a-f0-9]{4}(\.[a-f0-9]{4}){2})($|[^[:alnum:]_])'
private_hostname='(^|[^a-z0-9_.-])[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.(ts\.net|local)($|[^a-z0-9_.-]|\.($|[^a-z0-9_.-]))'
webhook_url='api2\.cursor\.sh/automations/webhook/'
usb_node='usbmodem[0-9]+'
ipv6_ula='(^|[^0-9a-z_:])fd[0-9a-f]{2}:(:|[0-9a-f])'
email_allowlist='^noreply@|@example\.(com|org)$'

# grep の「一致なし」だけを正常とみなす。
filter() {
    grep "$@" || [[ $? == 1 ]]
}

# 内容とファイル名の両方で一致した値を出力しない。
scan_text() {
    local findings
    findings=$(filter -aiEo -e "$private_ipv4" -e "$home_path" -e "$uuid" -e "$jp_phone" \
        -e "$mac_address" -e "$private_hostname" -e "$webhook_url" -e "$usb_node" -e "$ipv6_ula") || return $?
    if [[ -n $findings ]]; then
        printf '%s\n' 'アドレス・端末識別子・パス・電話番号・webhook URL の候補'
    fi
}

scan_email() {
    local findings
    findings=$(filter -aiEo "$email" | filter -ivE "$email_allowlist") || return $?
    if [[ -n $findings ]]; then
        printf '%s\n' 'メールアドレスの候補'
    fi
}

# ステージ済みの内容を検査し、検査ルールの定義行だけを除外する。
read_staged() {
    git show ":$1" | {
        case "$1" in
            scripts/check_pii.sh)
                filter -aEv "^(ipv4_octet|private_ipv4|home_path|uuid|jp_phone|email|email_allowlist|mac_address|private_hostname|webhook_url|usb_node|ipv6_ula)=('.*'|\".*\")$"
                ;;
            .gitleaks.toml)
                filter -aEv "^regex = '{3}.+'{3}$|^regexes = \['{3}.+'{3}\]$"
                ;;
            *) cat ;;
        esac
    }
}

scan_files() {
    local scan_content=$1
    local path label findings failed=0
    while IFS= read -r -d '' path; do
        label=$(printf '%q' "$path")
        findings=$(printf '%s\n' "$path" | scan_text) || return $?
        findings+=$(printf '%s\n' "$path" | scan_email) || return $?
        if [[ -n $findings ]]; then
            printf '%s\n' '追跡対象のファイル名に個人情報の候補があります。' >&2
            label='[伏字]'
            failed=1
        fi
        case "$path" in
            LICENSE|.gitignore|config/.env.example|uv.lock|firmware/dependencies.lock|firmware/partitions.csv|firmware/sdkconfig.defaults) ;;
            *)
                case $(printf '%s' "$path" | tr '[:upper:]' '[:lower:]') in
                    deploy/macos/com.grokwatch.gateway.plist.template|deploy/macos/install.sh|deploy/macos/uninstall.sh|deploy/macos/status.sh|deploy/macos/run-gateway.sh|deploy/macos/keychain-add.sh|deploy/macos/keychain.md|deploy/macos/tailscale-serve.md) ;;
                    *.md|*.sh|*.yml|*.yaml|*.toml|*.py|*.cpp|*.hpp|*/cmakelists.txt|cmakelists.txt|*.cmake|*.projbuild) ;;
                    *)
                        printf '許可リストにないファイル形式です。 %s\n' "$label" >&2
                        failed=1
                        continue
                        ;;
                esac
                ;;
        esac

        [[ $scan_content == yes ]] || continue
        findings=$(read_staged "$path" | scan_text) || return $?
        findings+=$(read_staged "$path" | scan_email) || return $?
        if [[ -n $findings ]]; then
            printf '内容に個人情報の候補があります。 %s\n' "$label" >&2
            failed=1
        fi
    done
    return "$failed"
}

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

case "${1:---staged}" in
    --staged)
        git ls-files --cached -z | scan_files yes
        ;;
    --history-paths)
        status=0
        git ls-files --cached -z | scan_files yes || status=$?
        # バイナリの差分を開かず、履歴上のファイル名と形式も検査する。
        git log --all --full-history -m --format= --name-only --no-renames --diff-filter=ACMRT -z |
            scan_files no || status=$?
        exit "$status"
        ;;
    *) exit 2 ;;
esac
