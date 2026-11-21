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
        assert not re.search(r"tailscale\s+funnel", source, re.IGNORECASE)
        assert not re.search(r"security[^\n]*[ \t]-w[ \t]+\S", source)
        assert not re.search(r"[A-Za-z0-9_-]{40,}", source)


def _fake_tools(directory):
    directory.mkdir()
    (directory / "uv").write_text("#!/bin/bash\nprintf '%s\\n' 'uv 0.13.9 (test)'\n")
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
    (directory / "launchctl").write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "case $1 in\n"
        "  print) [[ -f $LAUNCH_STATE ]] || exit 113; printf 'pid = 4242\\n' ;;\n"
        "  bootstrap) printf 'bootstrap\\n' >> $LAUNCH_LOG; : > $LAUNCH_STATE ;;\n"
        "  bootout) printf 'bootout\\n' >> $LAUNCH_LOG; rm -f $LAUNCH_STATE ;;\n"
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
    state = tmp_path / "launch-state"
    log = tmp_path / "launch-log"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.defpath)
    monkeypatch.setenv("LAUNCH_STATE", str(state))
    monkeypatch.setenv("LAUNCH_LOG", str(log))
    monkeypatch.setenv("PORT_PID", port_pid)
    monkeypatch.setenv("MISSING_ACCOUNT", missing_account)
    return home, state, log


def _install(home, *, dry_run=False, bridge="mock"):
    command = [
        "bash", str(DEPLOY / "install.sh"), "--bridge", bridge, "--repo", str(ROOT),
        "--whisper-model", str(home / "model.bin"),
    ]
    if dry_run:
        command.append("--dry-run")
    return subprocess.run(command, capture_output=True, text=True, env=os.environ.copy())


def test_install_dry_run_is_repeatable_and_never_writes_files(tmp_path, monkeypatch):
    home, _, _ = _install_env(tmp_path, monkeypatch)
    first = _install(home, dry_run=True)
    second = _install(home, dry_run=True)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert not (home / "Library").exists()


def test_install_reconciles_the_same_job_without_a_second_change(tmp_path, monkeypatch):
    home, _, log = _install_env(tmp_path, monkeypatch)
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


def test_uninstall_removes_only_its_job_and_plist_and_is_repeatable(tmp_path, monkeypatch):
    home, state, log = _install_env(tmp_path, monkeypatch)
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


def test_install_stops_for_a_foreign_listener_or_missing_keychain_item(tmp_path, monkeypatch):
    home, _, log = _install_env(tmp_path, monkeypatch, port_pid="9876")
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
    home, state, _ = _install_env(tmp_path, monkeypatch, port_pid="4242")
    state.touch()
    result = _install(home, dry_run=True)
    assert result.returncode == 0, result.stderr


def test_mock_bridge_does_not_require_webhook_keychain_items(tmp_path, monkeypatch):
    home, _, _ = _install_env(tmp_path, monkeypatch, missing_account="GROKWATCH_WEBHOOK_URL")
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
        "printf '%s\\n' \"${GROKWATCH_BRIDGE-unset}\" \"${GROKWATCH_DEVICE_TOKEN-unset}\" "
        "\"${GROKWATCH_WEBHOOK_URL-unset}\" \"${GROKWATCH_WEBHOOK_KEY-unset}\" "
        "\"${GROKWATCH_ALLOW_ENV_SECRETS-unset}\" > \"$RUNNER_OUTPUT\"\n"
        "printf '%s\\n' \"$@\" >> \"$RUNNER_OUTPUT\"\n"
    )
    uv.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "HOME": str(home), "RUNNER_OUTPUT": str(output),
        "GROKWATCH_BRIDGE_OVERRIDE": bridge,
        "GROKWATCH_DEVICE_TOKEN": "x" * 40,
        "GROKWATCH_WEBHOOK_URL": "https://placeholder.invalid/value",
        "GROKWATCH_WEBHOOK_KEY": "y" * 40,
        "GROKWATCH_ALLOW_ENV_SECRETS": "1",
    })
    result = subprocess.run(["bash", str(DEPLOY / "run-gateway.sh")], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    lines = output.read_text().splitlines()
    assert lines[:5] == [bridge, "unset", "unset", "unset", "unset"]
    assert lines[5:] == [
        "run", "--locked", "--project", str(ROOT / "gateway"), "--python", "3.11",
        "python", "-m", "grokwatch_gateway",
    ]


def test_python_ci_runs_repo_deployment_tests_for_both_versions():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "python: ['3.11', '3.13']" in workflow
    assert "pytest gateway/tests bridge/tests tests/e2e tests/repo" in workflow
