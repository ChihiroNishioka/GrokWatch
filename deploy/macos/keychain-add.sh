#!/usr/bin/env bash
set -euo pipefail

usage() {
	printf '%s\n' 'Usage: keychain-add.sh ACCOUNT | keychain-add.sh --file PATH ACCOUNT'
}

if (($# == 1)); then
	account=$1
	file=''
elif (($# == 3)) && [[ $1 == --file ]]; then
	file=$2
	account=$3
else
	usage >&2
	exit 64
fi

case $account in
	GROKWATCH_DEVICE_TOKEN|GROKWATCH_WEBHOOK_URL|GROKWATCH_WEBHOOK_KEY) ;;
	GROKWATCH_OPENAI_API_KEY|GROKWATCH_TASK_WEBHOOK_URL|GROKWATCH_TASK_WEBHOOK_KEY) ;;
	*) usage >&2; exit 64 ;;
esac

if [[ -z $file ]]; then
	exec security add-generic-password -s grokwatch -a "$account" -U -w
fi

exec python3 - "$account" "$file" <<'PY'
import errno
import os
import re
import select
import signal
import stat
import sys
import time
from pathlib import Path

account, filename = sys.argv[1:]
source = Path(filename)
descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
with os.fdopen(descriptor, "rb") as secret_file:
    source_stat = os.fstat(secret_file.fileno())
    mode = stat.S_IMODE(source_stat.st_mode)
    if not stat.S_ISREG(source_stat.st_mode) or mode & ~0o600:
        raise SystemExit("Secret file permissions must be no broader than 600")
    secret = bytearray(secret_file.read().rstrip(b"\r\n"))
if not secret or b"\0" in secret:
    raise SystemExit("Secret file is empty or invalid")

try:
    timeout = float(os.environ.get("GROKWATCH_TEST_KEYCHAIN_TIMEOUT_SECONDS", "15"))
except ValueError:
    raise SystemExit("Invalid Keychain prompt timeout")
if timeout <= 0:
    raise SystemExit("Invalid Keychain prompt timeout")

pid, terminal = os.forkpty()
if pid == 0:
    os.execvp("security", ["security", "add-generic-password", "-s", "grokwatch",
                            "-a", account, "-U", "-w"])

deadline = time.monotonic() + timeout
buffer = bytearray()
prompt_count = 0
status = None
child_reaped = False
failure = None
try:
    while status is None:
        waited, child_status = os.waitpid(pid, os.WNOHANG)
        if waited:
            status = child_status
            child_reaped = True
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure = "Keychain prompt timed out"
            break
        ready, _, _ = select.select([terminal], [], [], min(0.1, remaining))
        if not ready:
            continue
        try:
            chunk = os.read(terminal, 1024)
        except OSError as error:
            if error.errno == errno.EIO:
                continue
            raise
        if not chunk:
            continue
        buffer.extend(chunk)
        prompts = list(re.finditer(rb"(?:retype\s+)?password[^:\r\n]*:", buffer, re.IGNORECASE))
        consumed = 0
        for prompt in prompts:
            if prompt_count == 2:
                failure = "Unexpected extra Keychain prompt"
                break
            os.write(terminal, secret + b"\n")
            prompt_count += 1
            consumed = prompt.end()
        if consumed:
            del buffer[:consumed]
        if len(buffer) > 512:
            del buffer[:-256]
        if failure:
            break
    if status is not None:
        if prompt_count != 2:
            failure = "Keychain did not request both password entries"
        elif not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            failure = "Keychain update failed"
finally:
    os.close(terminal)
    if not child_reaped:
        try:
            os.kill(pid, signal.SIGKILL)
        except ChildProcessError:
            pass
        except ProcessLookupError:
            pass
        cleanup_deadline = time.monotonic() + 1
        while not child_reaped and time.monotonic() < cleanup_deadline:
            try:
                waited, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                break
            if waited:
                child_reaped = True
            else:
                time.sleep(min(0.01, cleanup_deadline - time.monotonic()))
    secret[:] = b"\0" * len(secret)

if failure:
    raise SystemExit(failure)
print(f"Stored Keychain item {account}")
PY
