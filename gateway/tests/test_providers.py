import asyncio
import json
from pathlib import Path
import secrets

import pytest

from support import eventually, process_gone


async def test_mock_stt_modes():
    from grokwatch_gateway.audio import MockStt, SttError

    assert await MockStt("聞こえた", delay=0.001)(b"") == "聞こえた"
    task = asyncio.create_task(MockStt(delay=60)(b""))
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(SttError):
        await MockStt(fail=True)(b"")


async def test_whisper_invocation_wav_and_cleanup(fake_commands):
    from grokwatch_gateway.audio import WhisperCpp

    assert await WhisperCpp(model="fixture-model")(b"\0" * 640) == "試験"
    args = json.loads((fake_commands / "whisper-cli.json").read_text())
    assert args == ["-m", "fixture-model", "-f", args[3], "-l", "ja", "-nt", "-otxt"]
    assert json.loads((fake_commands / "whisper.wav.json").read_text()) == [16000, 1, 2, 320]
    assert not Path(args[3]).parent.exists()


@pytest.mark.parametrize("mode", ["missing", "exit", "timeout"])
async def test_whisper_failures(fake_commands, monkeypatch, mode):
    from grokwatch_gateway.audio import SttError, WhisperCpp

    if mode == "exit":
        monkeypatch.setenv("GW_FIXTURE_WHISPER_CLI_EXIT", "1")
    if mode == "timeout":
        monkeypatch.setenv("GW_FIXTURE_WHISPER_CLI_DELAY", "60")
    with pytest.raises(SttError):
        await WhisperCpp(model="fixture-model", executable="absent" if mode == "missing" else "whisper-cli",
                         timeout=0.35)(b"\0" * 640)
    if mode != "missing":
        args = json.loads((fake_commands / "whisper-cli.json").read_text())
        assert not Path(args[3]).parent.exists()
        process_gone(fake_commands / "whisper-cli.pid")


async def test_mock_tts_deterministic():
    from grokwatch_gateway.audio import MockTts

    tts = MockTts()
    assert await tts("一") == await tts("一")
    assert 0 < len(await tts("一")) < len(await tts("一二三"))


@pytest.mark.parametrize("body", ["音声", '-v\n"引用"'])
async def test_say_invocation_no_text_in_argv(fake_commands, body):
    from grokwatch_gateway.audio import MacosSay

    assert await MacosSay()(body) == b"\1" * 642
    args = json.loads((fake_commands / "say.json").read_text())
    assert args == ["-v", "Kyoko", "-f", args[3], "--file-format=WAVE", "--data-format=LEI16@16000",
                    "-o", args[7]]
    assert (fake_commands / "say.input").read_text() == body
    assert not Path(args[3]).parent.exists()


@pytest.mark.parametrize("mode", ["1 2 8000", "2 2 16000", "1 1 16000", "exit", "timeout"])
async def test_say_failures_and_cleanup(fake_commands, monkeypatch, mode):
    from grokwatch_gateway.audio import MacosSay, TtsError

    key, value = {"exit": ("EXIT", "1"), "timeout": ("DELAY", "60")}.get(mode, ("FORMAT", mode))
    monkeypatch.setenv("GW_FIXTURE_SAY_" + key, value)
    with pytest.raises(TtsError):
        await MacosSay(timeout=0.35)("試験")
    args = json.loads((fake_commands / "say.json").read_text())
    assert not Path(args[3]).parent.exists()
    assert not Path(args[7]).exists()
    process_gone(fake_commands / "say.pid")


def test_secret_sources(fake_commands, monkeypatch):
    from grokwatch_gateway.config import Config

    fixture_token, fixture_key, env_key = (secrets.token_urlsafe(32) for _ in range(3))
    monkeypatch.setenv("GW_FIXTURE_SECURITY_GROKWATCH_DEVICE_TOKEN", fixture_token)
    monkeypatch.setenv("GW_FIXTURE_SECURITY_GROKWATCH_WEBHOOK_KEY", fixture_key)
    env = {"GROKWATCH_WEBHOOK_KEY": env_key, "GROKWATCH_DEVICE_TOKEN": fixture_token}
    assert Config.from_env(env).webhook_key == fixture_key
    assert json.loads((fake_commands / "security.json").read_text())[:4] == [
        "find-generic-password", "-s", "grokwatch", "-a",
    ]
    assert Config.from_env(env | {"GROKWATCH_ALLOW_ENV_SECRETS": "1"}).webhook_key == env_key
