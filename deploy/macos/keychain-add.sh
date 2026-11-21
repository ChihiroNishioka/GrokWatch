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
	*) usage >&2; exit 64 ;;
esac

if [[ -z $file ]]; then
	exec security add-generic-password -s grokwatch -a "$account" -U -w
fi

exec python3 - "$account" "$file" <<'PY'
import errno
import os
import select
import signal
import sys
import time
from pathlib import Path

account, filename = sys.argv[1:]
secret = Path(filename).read_bytes().rstrip(b"\r\n")
if not secret or b"\0" in secret:
    raise SystemExit("Secret file is empty or invalid")

pid, terminal = os.forkpty()
if pid == 0:
    os.execvp("security", ["security", "add-generic-password", "-s", "grokwatch",
                            "-a", account, "-U", "-w"])

deadline = time.monotonic() + 15
buffer = bytearray()
sent = False
try:
    while time.monotonic() < deadline:
        ready, _, _ = select.select([terminal], [], [], max(0, deadline - time.monotonic()))
        if not ready:
            break
        try:
            chunk = os.read(terminal, 1024)
        except OSError as error:
            if error.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        buffer.extend(chunk)
        if not sent and b"password" in buffer.lower():
            os.write(terminal, secret + b"\n")
            secret = b"\0" * len(secret)
            sent = True
    if not sent:
        os.kill(pid, signal.SIGTERM)
        raise SystemExit("Keychain prompt was not received")
    _, status = os.waitpid(pid, 0)
finally:
    os.close(terminal)
    if not sent:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
    raise SystemExit("Keychain update failed")
print(f"Stored Keychain item {account}")
PY
