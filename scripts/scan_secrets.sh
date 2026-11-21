#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

status=0
git diff -U0 --no-ext-diff --staged -- . >/dev/null
for config in .gitleaks-default.toml .gitleaks.toml; do
    gitleaks git --config "$config" --pre-commit --staged --redact=100 . || status=$?
done

commit_count=$(git rev-list --count --all)
pii_mode=--staged
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    [[ "$commit_count" -gt 0 ]] || exit 1
    # gitleaks が内部の Git エラーを成功扱いしても検査を通さない。
    git log -p -U0 --all >/dev/null
    for config in .gitleaks-default.toml .gitleaks.toml; do
        scan_status=0
        scan_output=$(gitleaks git --config "$config" --log-opts="--all" --redact=100 . 2>&1) || scan_status=$?
        printf '%s\n' "$scan_output"
        if [[ "$scan_status" != 0 ]]; then
            status=$scan_status
        else
            case "$scan_output" in
                *' 0 commits scanned.'*|*'failed to scan Git repository'*) status=1 ;;
            esac
        fi
    done
    pii_mode=--history-paths
else
    # 初回ステージに限り、履歴検査を省略できる。
    head_ref=$(git symbolic-ref --quiet HEAD) || exit 1
    if git show-ref --verify --quiet "$head_ref"; then
        exit 1
    else
        [[ $? == 1 ]] || exit 1
    fi
    [[ "$commit_count" == 0 ]] || exit 1
    printf '%s\n' '初回コミット前のため、ステージ済みファイルを検査します。'
fi

bash scripts/check_pii.sh "$pii_mode" || status=$?
exit "$status"
