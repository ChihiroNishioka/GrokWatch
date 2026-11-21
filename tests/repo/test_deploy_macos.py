import ast
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "macos"
LABEL = "com.grokwatch.gateway"
SCRIPT_NAMES = {
    "install.sh", "uninstall.sh", "status.sh", "run-gateway.sh", "keychain-add.sh",
}


def test_launch_agent_template_has_the_required_service_settings():
    template = DEPLOY / "com.grokwatch.gateway.plist.template"
    plist = plistlib.loads(template.read_bytes())
    assert plist["Label"] == LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["ThrottleInterval"] > 0
    assert plist["StandardOutPath"] == "@HOME@/Library/Logs/GrokWatch/gateway.out.log"
    assert plist["StandardErrorPath"] == "@HOME@/Library/Logs/GrokWatch/gateway.err.log"
    environment = plist["EnvironmentVariables"]
    assert environment == {
        "GROKWATCH_STT": "whisper_cpp",
        "GROKWATCH_TTS": "macos_say",
        "GROKWATCH_TTS_VOICE": "Kyoko",
        "GROKWATCH_BRIDGE": "@BRIDGE@",
        "GROKWATCH_LOG_TEXT": "0",
        "GROKWATCH_REPLY_LISTEN": "127.0.0.1:8767",
        "GROKWATCH_GATEWAY_PORT": "8765",
        "GROKWATCH_WHISPER_MODEL": "@WHISPER_MODEL@",
    }
    assert not {"GROKWATCH_DEVICE_TOKEN", "GROKWATCH_WEBHOOK_URL", "GROKWATCH_WEBHOOK_KEY"} & environment.keys()


def test_deployment_scripts_are_valid_and_use_fixed_targets():
    scripts = sorted(DEPLOY.glob("*.sh"))
    assert {script.name for script in scripts} == SCRIPT_NAMES
    for script in scripts:
        source = script.read_text()
        assert "set -euo pipefail" in source
        subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True, text=True)
        if shutil.which("shellcheck"):
            subprocess.run(["shellcheck", str(script)], check=True, capture_output=True, text=True)
        launchctl_lines = [
            line for line in source.splitlines()
            if re.search(r"\blaunchctl\s+(print|bootout|bootstrap)\b", line)
        ]
        if launchctl_lines:
            assert f"readonly LABEL='{LABEL}'" in source
        for line in launchctl_lines:
            assert '"$target"' in line or ('"$gui_domain"' in line and '"$plist_path"' in line)
            assert not re.search(r"launchctl .*[*?]", line)
        assert not re.search(r"tailscale\s+funnel\s+(?!status\b)", source, re.IGNORECASE)
        assert not re.search(r"security[^\n]*[ \t]-w[ \t]+\S", source)
        assert not re.search(r"[\"']-w[\"']\s*,\s*[\"'][^\"']+[\"']", source)
        if script.name == "keychain-add.sh":
            python_source = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
            tree = ast.parse(python_source)
            security_calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execvp" and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "security"
            ]
            assert len(security_calls) == 1
            argv = security_calls[0].args[1]
            assert isinstance(argv, ast.List)
            assert isinstance(argv.elts[-1], ast.Constant) and argv.elts[-1].value == "-w"
        assert not re.search(r"[A-Za-z0-9_-]{40,}", source)


@pytest.mark.parametrize(
    "mode, expected_status, expected_prompts",
    [("two", 0, 2), ("noisy_two", 0, 2), ("one", 1, 1), ("none", 1, 0)],
)
def test_keychain_file_answers_each_prompt_and_exits_without_hanging(
    tmp_path, mode, expected_status, expected_prompts,
):
    tools = tmp_path / "bin"
    tools.mkdir()
    trace = tmp_path / "security-result"
    (tools / "security").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        "mode = os.environ['FAKE_SECURITY_MODE']\n"
        "if sys.argv[1:] != ['add-generic-password', '-s', 'grokwatch', '-a', 'GROKWATCH_DEVICE_TOKEN', '-U', '-w']:\n"
        " with open(os.environ['FAKE_SECURITY_TRACE'], 'w') as result: result.write('invalid-argv')\n"
        " sys.exit(90)\n"
        "answers = []\n"
        "if mode == 'none':\n"
        " with open(os.environ['FAKE_SECURITY_TRACE'], 'w') as result: result.write('0:0')\n"
        " time.sleep(60)\n"
        "if mode in ('two', 'noisy_two', 'one'):\n"
        " print('password data for new item: ', end='', flush=True)\n"
        " if mode == 'noisy_two': print('x' * 700, end='', flush=True)\n"
        " answers.append(sys.stdin.readline().rstrip('\\r\\n'))\n"
        " if mode == 'one':\n"
        "  with open(os.environ['FAKE_SECURITY_TRACE'], 'w') as result: result.write('1:0')\n"
        "  time.sleep(60)\n"
        "if mode in ('two', 'noisy_two'):\n"
        " print('retype password for new item: ', end='', flush=True)\n"
        " answers.append(sys.stdin.readline().rstrip('\\r\\n'))\n"
        "with open(os.environ['FAKE_SECURITY_TRACE'], 'w') as result:\n"
        " result.write(f'{len(answers)}:{int(len(answers) == 2 and answers[0] == answers[1])}')\n"
        "sys.exit(0 if mode in ('two', 'noisy_two') and answers[0] == answers[1] else 0)\n"
    )
    (tools / "security").chmod(0o755)
    secret = tmp_path / "keychain-input"
    secret.write_text("sample-content\n")
    secret.chmod(0o600)
    env = os.environ.copy()
    env.update({
        "PATH": str(tools) + os.pathsep + os.defpath,
        "FAKE_SECURITY_MODE": mode,
        "FAKE_SECURITY_TRACE": str(trace),
        "GROKWATCH_TEST_KEYCHAIN_TIMEOUT_SECONDS": "0.25",
    })
    process = subprocess.Popen(
        ["bash", str(DEPLOY / "keychain-add.sh"), "--file", str(secret), "GROKWATCH_DEVICE_TOKEN"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        process.communicate()
        pytest.fail("keychain-add.sh did not finish within 3 seconds")
    assert process.returncode == expected_status, stderr
    assert trace.read_text() == f"{expected_prompts}:{int(mode in {'two', 'noisy_two'})}"


def test_keychain_file_rejects_permissions_wider_than_600(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    invoked = tmp_path / "security-invoked"
    (tools / "security").write_text("#!/bin/sh\ntouch \"$SECURITY_INVOKED\"\nexit 0\n")
    (tools / "security").chmod(0o755)
    secret = tmp_path / "keychain-input"
    secret.write_text("sample-content\n")
    secret.chmod(0o640)
    env = os.environ.copy()
    env["PATH"] = str(tools) + os.pathsep + os.defpath
    env["SECURITY_INVOKED"] = str(invoked)
    result = subprocess.run(
        ["bash", str(DEPLOY / "keychain-add.sh"), "--file", str(secret), "GROKWATCH_DEVICE_TOKEN"],
        capture_output=True, text=True, env=env, timeout=3,
    )
    assert result.returncode != 0
    assert not invoked.exists()
    assert not any(value in result.stderr for value in ("sample-content", "secret"))


def test_keychain_file_rejects_fifo_without_blocking(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    invoked = tmp_path / "security-invoked"
    (tools / "security").write_text("#!/bin/sh\ntouch \"$SECURITY_INVOKED\"\nexit 0\n")
    (tools / "security").chmod(0o755)
    secret = tmp_path / "keychain-input"
    os.mkfifo(secret)
    env = os.environ.copy()
    env["PATH"] = str(tools) + os.pathsep + os.defpath
    env["SECURITY_INVOKED"] = str(invoked)
    result = subprocess.run(
        ["bash", str(DEPLOY / "keychain-add.sh"), "--file", str(secret), "GROKWATCH_DEVICE_TOKEN"],
        capture_output=True, text=True, env=env, timeout=2,
    )
    assert result.returncode != 0
    assert not invoked.exists()


def _fake_tools(directory):
    directory.mkdir()
    (directory / "uv").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "if [[ ${1:-} == --version ]]; then printf '%s\\n' 'uv 0.13.9 (test)'; exit 0; fi\n"
        "if [[ ${1:-} == sync ]]; then printf 'sync\\n' >> $EVENT_LOG; printf '%s\\n' \"$@\" >> $UV_LOG; exit 0; fi\n"
        "exit 64\n"
    )
    (directory / "security").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "if [[ ${MISSING_ACCOUNT:-} == \"${@: -1}\" ]]; then exit 44; fi\n"
        "exit 0\n"
    )
    (directory / "lsof").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "if [[ -n ${PORT_PID:-} ]]; then printf '%s\\n' \"$PORT_PID\"; exit 0; fi\n"
        "exit 1\n"
    )
    (directory / "ps").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "pid=\"${@: -1}\"\n"
        "if [[ $pid == \"${CHILD_PID:-}\" && -n ${PARENT_PID:-} ]]; then printf '%s\\n' \"$PARENT_PID\"; else printf '1\\n'; fi\n"
    )
    (directory / "mktemp").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "touch \"$TMPDIR/mktemp-was-called\"\n"
        "exec /usr/bin/mktemp \"$@\"\n"
    )
    (directory / "launchctl").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "case $1 in\n"
        "  print)\n"
        "    [[ -f $LAUNCH_STATE ]] || exit 113\n"
        "    if [[ -f $LAUNCH_STOP_COUNT ]]; then\n"
        "      count=$(<\"$LAUNCH_STOP_COUNT\")\n"
        "      if ((count == 0)); then rm -f $LAUNCH_STATE $LAUNCH_STOP_COUNT; exit 113; fi\n"
        "      printf '%s\\n' \"$((count - 1))\" > $LAUNCH_STOP_COUNT\n"
        "    fi\n"
        "    printf 'pid = 4242\\n' ;;\n"
        "  bootstrap)\n"
        "    if [[ ${FAIL_BOOTSTRAP:-0} == 1 ]]; then exit 42; fi\n"
        "    printf 'bootstrap\\n' >> $LAUNCH_LOG; printf 'bootstrap\\n' >> $EVENT_LOG; : > $LAUNCH_STATE ;;\n"
        "  bootout)\n"
        "    printf 'bootout\\n' >> $LAUNCH_LOG; printf 'bootout\\n' >> $EVENT_LOG\n"
        "    if (( ${STOP_DELAY_PRINTS:-0} > 0 )); then printf '%s\\n' \"$STOP_DELAY_PRINTS\" > $LAUNCH_STOP_COUNT; else rm -f $LAUNCH_STATE; fi ;;\n"
        "  *) exit 64 ;;\n"
        "esac\n"
    )
    for tool in directory.iterdir():
        tool.chmod(0o755)


def _install_env(tmp_path, monkeypatch, *, port_pid="", missing_account=""):
    tools = tmp_path / "bin"
    _fake_tools(tools)
    home = tmp_path / "home"
    home.mkdir()
    (home / "model.bin").write_bytes(b"model")
    temp = tmp_path / "tmp"
    temp.mkdir()
    state = tmp_path / "launch-state"
    log = tmp_path / "launch-log"
    events = tmp_path / "events"
    uv_log = tmp_path / "uv-log"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.defpath)
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setenv("LAUNCH_STATE", str(state))
    monkeypatch.setenv("LAUNCH_LOG", str(log))
    monkeypatch.setenv("LAUNCH_STOP_COUNT", str(tmp_path / "stop-count"))
    monkeypatch.setenv("EVENT_LOG", str(events))
    monkeypatch.setenv("UV_LOG", str(uv_log))
    monkeypatch.setenv("PORT_PID", port_pid)
    monkeypatch.setenv("MISSING_ACCOUNT", missing_account)
    monkeypatch.setenv("CHILD_PID", "")
    monkeypatch.setenv("PARENT_PID", "")
    monkeypatch.setenv("STOP_DELAY_PRINTS", "0")
    monkeypatch.setenv("FAIL_BOOTSTRAP", "0")
    return home, state, log, temp, events, uv_log


def _install(home, *, dry_run=False, bridge="mock"):
    command = [
        "bash", str(DEPLOY / "install.sh"), "--bridge", bridge, "--repo", str(ROOT),
        "--whisper-model", str(home / "model.bin"),
    ]
    if dry_run:
        command.append("--dry-run")
    return subprocess.run(command, capture_output=True, text=True, env=os.environ.copy())


def test_install_dry_run_is_repeatable_and_never_writes_files(tmp_path, monkeypatch):
    home, _, _, temp, _, _ = _install_env(tmp_path, monkeypatch)
    first = _install(home, dry_run=True)
    second = _install(home, dry_run=True)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert not (home / "Library").exists()
    assert list(temp.iterdir()) == []
    assert "<<" not in (DEPLOY / "install.sh").read_text()


def test_install_reconciles_the_same_job_without_a_second_change(tmp_path, monkeypatch):
    home, _, log, _, _, _ = _install_env(tmp_path, monkeypatch)
    first = _install(home)
    assert first.returncode == 0, first.stderr
    plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    original = plist_path.read_bytes()
    actions = log.read_text()
    second = _install(home)
    assert second.returncode == 0, second.stderr
    assert plist_path.read_bytes() == original
    assert log.read_text() == actions
    assert actions.splitlines() == ["bootstrap"]


def test_install_creates_log_directory_when_loading_an_existing_plist(tmp_path, monkeypatch):
    home, state, _, _, _, _ = _install_env(tmp_path, monkeypatch)
    first = _install(home)
    assert first.returncode == 0, first.stderr
    state.unlink()
    logs = home / "Library" / "Logs" / "GrokWatch"
    logs.rmdir()
    loaded = _install(home)
    assert loaded.returncode == 0, loaded.stderr
    assert logs.is_dir()
    assert logs.stat().st_mode & 0o777 == 0o700


def test_uninstall_removes_only_its_job_and_plist_and_is_repeatable(tmp_path, monkeypatch):
    home, state, log, _, _, _ = _install_env(tmp_path, monkeypatch)
    launch_agents = home / "Library" / "LaunchAgents"
    logs = home / "Library" / "Logs" / "GrokWatch"
    launch_agents.mkdir(parents=True)
    logs.mkdir(parents=True)
    plist = launch_agents / f"{LABEL}.plist"
    plist.write_text("service")
    (logs / "gateway.out.log").write_text("keep")
    state.touch()

    dry_run = subprocess.run(
        ["bash", str(DEPLOY / "uninstall.sh"), "--dry-run"],
        capture_output=True, text=True, env=os.environ.copy(),
    )
    assert dry_run.returncode == 0
    assert plist.exists()

    command = ["bash", str(DEPLOY / "uninstall.sh")]
    first = subprocess.run(command, capture_output=True, text=True, env=os.environ.copy())
    actions = log.read_text()
    second = subprocess.run(command, capture_output=True, text=True, env=os.environ.copy())
    assert first.returncode == second.returncode == 0
    assert not plist.exists()
    assert (logs / "gateway.out.log").read_text() == "keep"
    assert log.read_text() == actions == "bootout\n"


@pytest.mark.parametrize(
    "funnel_json, warning",
    [(None, False), ('{"AllowFunnel":{}}', False), ('{"AllowFunnel":{"test:443":true}}', True)],
)
def test_status_warns_when_funnel_is_active_and_skips_when_tailscale_is_missing(
    tmp_path, funnel_json, warning,
):
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, content in {
        "id": "#!/bin/sh\nprintf '501\\n'\n",
        "launchctl": "#!/bin/sh\nexit 1\n",
        "lsof": "#!/bin/sh\nexit 1\n",
        "curl": "#!/bin/sh\nexit 1\n",
        "security": "#!/bin/sh\nexit 1\n",
    }.items():
        command = tools / name
        command.write_text(content)
        command.chmod(0o755)
    if funnel_json is not None:
        tailscale = tools / "tailscale"
        tailscale.write_text(
            "#!/bin/sh\n"
            "if [ \"$1 $2\" = 'funnel status' ]; then printf '%s\\n' \"$FUNNEL_JSON\"; fi\n"
        )
        tailscale.chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": str(tools) + os.pathsep + os.defpath})
    if funnel_json is not None:
        env["FUNNEL_JSON"] = funnel_json
    result = subprocess.run(
        ["bash", str(DEPLOY / "status.sh")], capture_output=True, text=True, env=env, timeout=3,
    )
    assert result.returncode == 0
    assert ("WARNING: Funnel is active" in result.stdout) is warning
    if funnel_json is None:
        assert "Tailscale Serve: unavailable" in result.stdout


def test_install_stops_for_a_foreign_listener_or_missing_keychain_item(tmp_path, monkeypatch):
    home, _, log, _, _, _ = _install_env(tmp_path, monkeypatch, port_pid="9876")
    occupied = _install(home, dry_run=True)
    assert occupied.returncode != 0
    assert "8765" in occupied.stderr or "8767" in occupied.stderr
    assert not log.exists()

    monkeypatch.setenv("PORT_PID", "")
    monkeypatch.setenv("MISSING_ACCOUNT", "GROKWATCH_DEVICE_TOKEN")
    missing = _install(home, dry_run=True)
    assert missing.returncode != 0
    assert "GROKWATCH_DEVICE_TOKEN" in missing.stderr
    assert not any(value in missing.stderr for value in ("secret", "token-value", "https://"))


def test_install_allows_ports_owned_by_its_job(tmp_path, monkeypatch):
    home, state, _, _, _, _ = _install_env(tmp_path, monkeypatch, port_pid="4242")
    state.touch()
    result = _install(home, dry_run=True)
    assert result.returncode == 0, result.stderr


def test_install_allows_a_listener_descended_from_its_job(tmp_path, monkeypatch):
    home, state, _, _, _, _ = _install_env(tmp_path, monkeypatch, port_pid="5252")
    state.touch()
    monkeypatch.setenv("CHILD_PID", "5252")
    monkeypatch.setenv("PARENT_PID", "4242")
    result = _install(home, dry_run=True)
    assert result.returncode == 0, result.stderr


def test_install_waits_for_changed_job_to_stop_before_bootstrap(tmp_path, monkeypatch):
    home, _, log, _, events, uv_log = _install_env(tmp_path, monkeypatch)
    first = _install(home, bridge="mock")
    assert first.returncode == 0, first.stderr
    monkeypatch.setenv("STOP_DELAY_PRINTS", "2")
    changed = _install(home, bridge="webhook")
    assert changed.returncode == 0, changed.stderr
    assert log.read_text().splitlines() == ["bootstrap", "bootout", "bootstrap"]
    assert events.read_text().splitlines() == ["sync", "bootstrap", "sync", "bootout", "bootstrap"]
    assert uv_log.read_text().splitlines() == ["sync", "--locked", "--python", "3.11",
                                                "--project", str(ROOT)] * 2
    assert not (tmp_path / "stop-count").exists()
    installed = (home / "Library" / "LaunchAgents" / f"{LABEL}.plist").read_text()
    assert "webhook" in installed and "mock" not in installed


def test_install_reports_bootstrap_failure(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _install_env(tmp_path, monkeypatch)
    monkeypatch.setenv("FAIL_BOOTSTRAP", "1")
    result = _install(home)
    assert result.returncode != 0
    assert "Failed to load LaunchAgent" in result.stderr


def test_mock_bridge_does_not_require_webhook_keychain_items(tmp_path, monkeypatch):
    home, _, _, _, _, _ = _install_env(tmp_path, monkeypatch, missing_account="GROKWATCH_WEBHOOK_URL")
    mock = _install(home, dry_run=True)
    webhook = _install(home, dry_run=True, bridge="webhook")
    assert mock.returncode == 0, mock.stderr
    assert webhook.returncode != 0
    assert "GROKWATCH_WEBHOOK_URL" in webhook.stderr


@pytest.mark.parametrize("bridge", ["mock", "webhook"])
def test_runner_selects_the_bridge_and_removes_secret_environment(tmp_path, bridge):
    home = tmp_path / "home"
    uv = home / ".local" / "bin" / "uv"
    uv.parent.mkdir(parents=True)
    output = tmp_path / "runner-output"
    uv.write_text(
        "#!/bin/bash\n"
        "if [[ ${1:-} == --version ]]; then printf '%s\\n' 'uv 0.13.9 (test)'; exit 0; fi\n"
        "printf '%s\\n' \"$$\" \"${GROKWATCH_BRIDGE-unset}\" "
        "\"${GROKWATCH_DEVICE_TOKEN-unset}\" \"${GROKWATCH_WEBHOOK_URL-unset}\" "
        "\"${GROKWATCH_WEBHOOK_KEY-unset}\" \"${GROKWATCH_ALLOW_ENV_SECRETS-unset}\" > \"$RUNNER_OUTPUT\"\n"
        "printf '%s\\n' \"$@\" >> \"$RUNNER_OUTPUT\"\n"
    )
    uv.chmod(0o755)
    repo = tmp_path / "repo"
    runner_dir = repo / "deploy" / "macos"
    runner_dir.mkdir(parents=True)
    shutil.copy2(DEPLOY / "run-gateway.sh", runner_dir / "run-gateway.sh")
    python = repo / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        "#!/bin/bash\n"
        "if [[ ${1:-} == --version ]]; then printf '%s\\n' 'Python 3.11.8'; exit 0; fi\n"
        "printf '%s\\n' \"$$\" \"${GROKWATCH_BRIDGE-unset}\" \"${GROKWATCH_DEVICE_TOKEN-unset}\" "
        "\"${GROKWATCH_WEBHOOK_URL-unset}\" \"${GROKWATCH_WEBHOOK_KEY-unset}\" "
        "\"${GROKWATCH_ALLOW_ENV_SECRETS-unset}\" > \"$RUNNER_OUTPUT\"\n"
        "printf '%s\\n' \"$@\" >> \"$RUNNER_OUTPUT\"\n"
    )
    python.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "HOME": str(home), "RUNNER_OUTPUT": str(output), "PATH": os.defpath,
        "GROKWATCH_BRIDGE_OVERRIDE": bridge,
        "GROKWATCH_DEVICE_TOKEN": "x" * 40,
        "GROKWATCH_WEBHOOK_URL": "https://placeholder.invalid/value",
        "GROKWATCH_WEBHOOK_KEY": "y" * 40,
        "GROKWATCH_ALLOW_ENV_SECRETS": "1",
    })
    process = subprocess.Popen(
        ["bash", str(runner_dir / "run-gateway.sh")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    stdout, stderr = process.communicate(timeout=3)
    assert process.returncode == 0, stderr
    lines = output.read_text().splitlines()
    assert lines[:6] == [str(process.pid), bridge, "unset", "unset", "unset", "unset"]
    assert lines[6:] == ["-m", "grokwatch_gateway"]


def test_python_ci_runs_repo_deployment_tests_for_both_versions():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "python: ['3.11', '3.13']" in workflow
    assert "pytest gateway/tests bridge/tests tests/e2e tests/repo" in workflow


def test_setup_includes_the_exact_serve_backend_path():
    setup = (ROOT / "docs" / "SETUP.md").read_text()
    assert "tailscale serve --bg --https=443 --set-path=/v1/reply http://127.0.0.1:8767/v1/reply" in setup
    assert "../deploy/macos/tailscale-serve.md" in setup
