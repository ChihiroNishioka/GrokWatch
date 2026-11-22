import os
from pathlib import Path
import plistlib
import re
import subprocess

import pytest

from test_deploy_macos import DEPLOY, LABEL, ROOT, _install, _install_env

TOOL = ROOT / "tools" / "grokwatch-context"
OPENAI = "sk-" + "a" * 30
TASK_URL = "https://hooks.invalid/task/" + "b" * 20
TASK_KEY = "k" * 24


def _fake_swiftc(tools: Path):
    swiftc = tools / "swiftc"
    swiftc.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "printf '%s\\n' \"$@\" > \"$SWIFTC_LOG\"\n"
        "out=''\nwhile (($#)); do if [[ $1 == -o ]]; then out=$2; fi; shift; done\n"
        "if [[ ${FAIL_SWIFTC:-0} == 1 ]]; then exit 1; fi\n"
        "printf 'binary' > \"$out\"\n"
    )
    swiftc.chmod(0o755)


def _realtime_env(tmp_path, monkeypatch, *, swiftc=True, **kwargs):
    result = _install_env(tmp_path, monkeypatch, **kwargs)
    if swiftc:
        _fake_swiftc(tmp_path / "bin")
    monkeypatch.setenv("SWIFTC_LOG", str(tmp_path / "swiftc-log"))
    monkeypatch.setenv("FAIL_SWIFTC", "0")
    return result


def test_realtime_install_builds_helper_and_passes_its_path(tmp_path, monkeypatch):
    home, _, log, _, _, _ = _realtime_env(tmp_path, monkeypatch)
    result = _install(home, bridge="realtime")
    assert result.returncode == 0, result.stderr
    binary = home / ".local" / "share" / "GrokWatch" / "bin" / "grokwatch-context"
    assert binary.read_bytes() == b"binary" and os.access(binary, os.X_OK)
    args = (tmp_path / "swiftc-log").read_text().splitlines()
    assert "-O" in args and str(TOOL / "main.swift") in args
    assert ["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT", "-Xlinker", "__info_plist",
            "-Xlinker", str(TOOL / "Info.plist")] == args[args.index("-Xlinker"):args.index("-Xlinker") + 8]
    plist = plistlib.loads((home / "Library" / "LaunchAgents" / f"{LABEL}.plist").read_bytes())
    environment = plist["EnvironmentVariables"]
    assert environment["GROKWATCH_BRIDGE"] == "realtime"
    assert environment["GROKWATCH_CONTEXT_BIN"] == str(binary)
    assert log.read_text().splitlines() == ["bootstrap"]


def test_realtime_dry_run_does_not_build(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _realtime_env(tmp_path, monkeypatch)
    result = _install(home, bridge="realtime", dry_run=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "swiftc-log").exists()
    assert not (home / ".local").exists()


def test_realtime_requires_swiftc_and_reports_it_clearly(tmp_path, monkeypatch):
    home, _, log, _, _, _ = _realtime_env(tmp_path, monkeypatch, swiftc=False)
    result = _install(home, bridge="realtime")
    assert result.returncode == 69
    assert "swiftc" in result.stderr
    assert not log.exists()


def test_realtime_build_failure_stops_before_touching_the_service(tmp_path, monkeypatch):
    home, _, log, _, _, _ = _realtime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("FAIL_SWIFTC", "1")
    result = _install(home, bridge="realtime")
    assert result.returncode == 69
    assert "grokwatch-context" in result.stderr
    assert not log.exists()
    assert not (home / "Library" / "LaunchAgents").exists()


def test_realtime_requires_the_openai_key_but_only_warns_for_task_items(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _realtime_env(tmp_path, monkeypatch, missing_account="GROKWATCH_OPENAI_API_KEY")
    missing = _install(home, bridge="realtime", dry_run=True)
    assert missing.returncode == 78
    assert "GROKWATCH_OPENAI_API_KEY" in missing.stderr

    monkeypatch.setenv("MISSING_ACCOUNT", "GROKWATCH_TASK_WEBHOOK_URL")
    optional = _install(home, bridge="realtime", dry_run=True)
    assert optional.returncode == 0, optional.stderr
    assert "GROKWATCH_TASK_WEBHOOK_URL" in optional.stderr

    monkeypatch.setenv("MISSING_ACCOUNT", "GROKWATCH_WEBHOOK_URL")
    no_legacy = _install(home, bridge="realtime", dry_run=True)
    assert no_legacy.returncode == 0, no_legacy.stderr


def test_mock_and_webhook_do_not_build_the_helper(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _realtime_env(tmp_path, monkeypatch)
    assert _install(home, bridge="mock").returncode == 0
    assert not (tmp_path / "swiftc-log").exists()


def test_install_rejects_unknown_bridges(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _realtime_env(tmp_path, monkeypatch)
    assert _install(home, bridge="other", dry_run=True).returncode == 64


@pytest.mark.parametrize("account", [
    "GROKWATCH_OPENAI_API_KEY", "GROKWATCH_TASK_WEBHOOK_URL", "GROKWATCH_TASK_WEBHOOK_KEY",
])
def test_keychain_add_accepts_the_realtime_accounts(tmp_path, account):
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "security").write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$SECURITY_ARGS\"\nexit 0\n")
    (tools / "security").chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": str(tools) + os.pathsep + os.defpath, "SECURITY_ARGS": str(tmp_path / "args")})
    result = subprocess.run(["bash", str(DEPLOY / "keychain-add.sh"), account],
                            capture_output=True, text=True, env=env, timeout=5)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "args").read_text().split() == [
        "add-generic-password", "-s", "grokwatch", "-a", account, "-U", "-w"]
    rejected = subprocess.run(["bash", str(DEPLOY / "keychain-add.sh"), "GROKWATCH_OTHER"],
                              capture_output=True, text=True, env=env, timeout=5)
    assert rejected.returncode == 64


def test_status_reports_the_new_items_without_values(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, content in {
        "id": "#!/bin/sh\nprintf '501\\n'\n",
        "launchctl": "#!/bin/sh\nexit 1\n",
        "lsof": "#!/bin/sh\nexit 1\n",
        "curl": "#!/bin/sh\nexit 1\n",
        "security": "#!/bin/sh\n[ \"$5\" = GROKWATCH_OPENAI_API_KEY ] && exit 0\nexit 44\n",
    }.items():
        (tools / name).write_text(content)
        (tools / name).chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": str(tools) + os.pathsep + os.defpath, "HOME": str(tmp_path)})
    result = subprocess.run(["bash", str(DEPLOY / "status.sh")], capture_output=True, text=True,
                            env=env, timeout=5)
    assert result.returncode == 0
    assert "Keychain GROKWATCH_OPENAI_API_KEY: present" in result.stdout
    assert "Keychain GROKWATCH_TASK_WEBHOOK_URL: missing" in result.stdout
    assert "Keychain GROKWATCH_TASK_WEBHOOK_KEY: missing" in result.stdout
    assert "grokwatch-context: missing" in result.stdout


def _keys_run(tmp_path, answers, *, fail_security=False):
    tools = tmp_path / "bin"
    tools.mkdir(exist_ok=True)
    trace = tmp_path / "saved"
    (tools / "security").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "account = sys.argv[sys.argv.index('-a') + 1]\n"
        "print('password data for new item: ', end='', flush=True)\n"
        "first = sys.stdin.readline().rstrip('\\r\\n')\n"
        "print('retype password for new item: ', end='', flush=True)\n"
        "second = sys.stdin.readline().rstrip('\\r\\n')\n"
        "assert first == second\n"
        "with open(os.environ['FAKE_TRACE'], 'a') as out: out.write(account + '=' + first + '\\n')\n"
    )
    (tools / "security").chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": str(tools) + os.pathsep + os.defpath, "FAKE_TRACE": str(trace),
                "TMPDIR": str(tmp_path)})
    result = subprocess.run(
        ["bash", str(DEPLOY / "set-realtime-keys.sh")], input="\n".join(answers) + "\n",
        capture_output=True, text=True, env=env, timeout=20,
    )
    saved = dict(line.split("=", 1) for line in trace.read_text().splitlines()) if trace.exists() else {}
    return result, saved


def _no_values(result, *values):
    for value in values:
        assert value not in result.stdout and value not in result.stderr


def test_keys_script_saves_all_three_items_and_never_prints_values(tmp_path):
    result, saved = _keys_run(tmp_path, [OPENAI, OPENAI, TASK_URL, TASK_URL, TASK_KEY, TASK_KEY])
    assert result.returncode == 0, result.stderr
    assert saved == {
        "GROKWATCH_OPENAI_API_KEY": OPENAI,
        "GROKWATCH_TASK_WEBHOOK_URL": TASK_URL,
        "GROKWATCH_TASK_WEBHOOK_KEY": TASK_KEY,
    }
    _no_values(result, OPENAI, TASK_URL, TASK_KEY)
    assert "bash deploy/macos/install.sh --bridge realtime" in result.stdout
    assert "Mac のログインパスワードや暗証番号ではありません" in result.stdout
    assert not list(tmp_path.glob("tmp.*"))


def test_keys_script_can_skip_the_optional_task_routine(tmp_path):
    result, saved = _keys_run(tmp_path, [OPENAI, OPENAI, ""])
    assert result.returncode == 0, result.stderr
    assert saved == {"GROKWATCH_OPENAI_API_KEY": OPENAI}
    _no_values(result, OPENAI)


@pytest.mark.parametrize("answers, message", [
    (["sk-short", "sk-short"], "API キーではない"),
    (["x" * 30, "x" * 30], "API キーではない"),
    (["https://example.invalid/" + "a" * 30] * 2, "URL が入っています"),
    ([OPENAI, "sk-" + "b" * 30], "1回目と2回目が違います"),
    ([OPENAI, OPENAI, "http://hooks.invalid/" + "c" * 20, "http://hooks.invalid/" + "c" * 20], "URL ではない"),
    ([OPENAI, OPENAI, TASK_URL, TASK_URL, "short", "short"], "短すぎます"),
    ([OPENAI, OPENAI, TASK_URL, TASK_URL, TASK_URL, TASK_URL], "URL が入っています"),
    ([OPENAI, OPENAI, TASK_URL, TASK_URL, OPENAI, OPENAI], "同じ値"),
])
def test_keys_script_rejects_bad_input_and_saves_nothing(tmp_path, answers, message):
    result, saved = _keys_run(tmp_path, answers)
    assert result.returncode == 1
    assert message in result.stdout
    assert saved == {}
    _no_values(result, *{a for a in answers if a})


def test_keys_script_has_no_command_line_secrets_or_echo():
    source = (DEPLOY / "set-realtime-keys.sh").read_text()
    assert source.count("read -r -s") >= 2
    assert "keychain-add.sh\" --file" in source
    assert "umask 077" in source and "chmod 600" in source
    assert not re.search(r"echo[^\n]*\$\{?(openai|url|key)\b", source)


def test_grant_context_reports_counts_only(tmp_path):
    binary = tmp_path / "grokwatch-context"
    binary.write_text(
        "#!/bin/bash\n"
        "case $1 in\n"
        "  schedule) printf '%s\\n' '{\"events\":[{\"title\":\"SECRET-TITLE\"},{\"title\":\"x\"}]}' ;;\n"
        "  mail) if [[ ${MAIL_EXIT:-0} != 0 ]]; then exit \"$MAIL_EXIT\"; fi\n"
        "        printf '%s\\n' '{\"messages\":[{\"subject\":\"SECRET-SUBJECT\"}]}' ;;\n"
        "esac\n"
    )
    binary.chmod(0o755)
    env = os.environ.copy()
    env["GROKWATCH_CONTEXT_BIN"] = str(binary)
    ok = subprocess.run(["bash", str(DEPLOY / "grant-context.sh")], capture_output=True, text=True,
                        env=env, timeout=20)
    assert ok.returncode == 0, ok.stderr
    assert "2 件" in ok.stdout and "1 件" in ok.stdout
    assert "SECRET" not in ok.stdout + ok.stderr
    env["MAIL_EXIT"] = "4"
    not_running = subprocess.run(["bash", str(DEPLOY / "grant-context.sh")], capture_output=True,
                                 text=True, env=env, timeout=20)
    assert not_running.returncode == 1
    assert "メール.app が起動していません" in not_running.stdout
    env["MAIL_EXIT"] = "3"
    denied = subprocess.run(["bash", str(DEPLOY / "grant-context.sh")], capture_output=True,
                            text=True, env=env, timeout=20)
    assert denied.returncode == 1 and "許可されていません" in denied.stdout


def test_swift_source_follows_the_gateway_contract():
    source = (TOOL / "main.swift").read_text()
    for needle in ('"schedule"', '"mail"', '"--version"', '"--from"', '"--to"', '"--since-hours"',
                   '"--limit"', '"--unread-only"', "fail(3", "fail(4", "fail(64", "usageFailure",
                   "requestFullAccessToEvents", "com.apple.mail", "NSAppleScript", "-1743",
                   "JSONSerialization", "maxEvents = 30", "\"all_day\"", '"events"', '"messages"',
                   '"received"', '"calendar"', '"location"', "ASCII character 31",
                   "ASCII character 30", "timeout: .now() + 30"):
        assert needle in source, needle
    assert "launchApplication" not in source and "openApplication" not in source
    script = source[source.index("func mailScript"):source.index("func runMail")]
    assert "content of" not in script and "content" not in script.lower()
    assert "source of" not in script and "attachment" not in script
    assert "sender of m" in script and "subject of m" in script and "date received of m" in script
    assert "tell application \"Mail\"" in script
    assert "send" not in script.lower().replace("sender", "")
    assert "import Foundation" in source and "import EventKit" in source
    assert not re.search(r"^import (?!AppKit|EventKit|Foundation)", source, re.MULTILINE)


def test_swift_version_matches_the_release_and_info_plist_has_usage_texts():
    release = subprocess.run(["python3", str(ROOT / "scripts" / "release_version.py")],
                             capture_output=True, text=True, check=True).stdout.strip()
    assert f'let toolVersion = "{release}"' in (TOOL / "main.swift").read_text()
    plist = plistlib.loads((TOOL / "Info.plist").read_bytes())
    assert plist["NSCalendarsFullAccessUsageDescription"].strip()
    assert plist["NSAppleEventsUsageDescription"].strip()
    assert plist["CFBundleShortVersionString"] == release


def test_install_embeds_the_info_plist_and_targets_macos_14():
    source = (DEPLOY / "install.sh").read_text()
    for needle in ("-sectcreate", "__TEXT", "__info_plist", "macos14.0", "-O",
                   ".local/share/GrokWatch/bin"):
        assert needle in source


def test_release_version_script_passes_at_1_2_0():
    result = subprocess.run(["python3", str(ROOT / "scripts" / "release_version.py")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1.2.1"
