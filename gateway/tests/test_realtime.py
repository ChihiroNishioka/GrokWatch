import asyncio
import base64
from contextlib import asynccontextmanager
import json
import secrets

import pytest

from grokwatch_bridge.contract import Health, ReplyChunk
from realtime_fake import FakeHttp, FakeRealtime, SPEECH, delta, done, helper_calls, make_helper
from support import connected, eventually, gateway


class FallbackBridge:
    name = "webhook"

    def __init__(self):
        self.texts = []

    async def health(self):
        return Health(True)

    async def cancel(self, session):
        pass

    async def send_utterance(self, text, session):
        self.texts.append(text)
        yield ReplyChunk("従来経路の返事")


@asynccontextmanager
async def realtime(tmp_path, scripts=(), *, bridge=None, helper=None, task=True, http=None, fake=None, **settings):
    fake = fake or FakeRealtime(scripts)
    http = http or FakeHttp()
    helper = helper or make_helper(tmp_path / "context")
    key = secrets.token_urlsafe(24)
    async with fake.serve() as ws_url, http.serve() as http_base:
        options = dict(
            bridge_name="realtime", openai_api_key=key, realtime_url=ws_url,
            responses_url=http_base + "/v1/responses", context_bin=str(helper),
            webhook_allow_loopback_http=True, realtime_idle=60,
        )
        if task:
            options.update(task_webhook_url=http_base + "/task", task_webhook_key="task-" + key)
        options.update(settings)
        async with gateway(bridge=bridge, **options) as (app, config, client, base, reply):
            fake.reply_base = reply
            yield app, config, client, base, fake, http, helper


async def talk(device, frames=15):
    await device.start()
    await device.stop(frames)
    return await device.idle()


def kinds(messages):
    return [m["type"] if isinstance(m, dict) and "type" in m else ("bytes" if isinstance(m, bytes) else m)
            for m in messages]


def tool_outputs(fake):
    return [json.loads(e["item"]["output"]) for e in fake.events("conversation.item.create")]


async def test_session_update_audio_and_speech(tmp_path):
    async with realtime(tmp_path) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            messages = await talk(device)
        assert fake.headers[0]["Authorization"] == "Bearer " + config.openai_api_key
        assert fake.queries[0] == {"model": "gpt-realtime-2.1"}
        session = fake.events("session.update")[0]["session"]
        assert session["type"] == "realtime" and session["output_modalities"] == ["audio"]
        assert session["audio"]["input"] == {"format": {"type": "audio/pcm", "rate": 24000}, "turn_detection": None}
        assert session["audio"]["output"] == {"format": {"type": "audio/pcm", "rate": 24000}, "voice": "marin"}
        assert session["tool_choice"] == "auto"
        assert {t["name"] for t in session["tools"]} == {"get_schedule", "get_mail", "web_search", "delegate_to_grok_bot"}
        assert all(t["type"] == "function" for t in session["tools"])
        text = session["instructions"]
        assert "Grok Bot" in text and "年" in text and "delegate_to_grok_bot" in text
        assert "決して delegate_to_grok_bot に渡さない" in text and "それはチャットで頼んでね" in text
        for word in ("送信", "削除", "購入", "支払い", "予約の確定"):
            assert word in text

        received = [e["type"] for e in fake.received]
        appended = fake.events("input_audio_buffer.append")
        assert len(appended) == 15
        sizes = [len(base64.b64decode(e["audio"])) for e in appended]
        assert all(size % 2 == 0 for size in sizes) and abs(sum(sizes) - 15 * 960) <= 4  # 16 kHz -> 24 kHz
        tail = received[received.index("input_audio_buffer.commit"):]
        assert tail == ["input_audio_buffer.commit", "response.create"]
        assert received.index("input_audio_buffer.commit") > max(
            i for i, kind in enumerate(received) if kind == "input_audio_buffer.append")

    states = [m for m in messages if isinstance(m, dict) and m["type"] == "state"]
    assert [m["state"] for m in states] == ["speaking", "idle"]
    start = next(m for m in messages if isinstance(m, dict) and m["type"] == "tts_start")
    assert start == {"type": "tts_start", "sample_rate": 16000, "emotion": "neutral"}
    frames = [m for m in messages if isinstance(m, bytes)]
    assert len(frames) == 10 and all(len(f) == 640 for f in frames)  # 2 x 100 ms of 24 kHz audio -> 16 kHz
    assert kinds(messages).index("tts_start") < kinds(messages).index("bytes") < kinds(messages).index("tts_end")


async def test_function_calls_round_trip(tmp_path):
    scripts = [
        [done(("get_schedule", "c1", {"from": "2026-11-22", "to": "2026-11-23"}),
              ("get_mail", "c2", {"unread_only": False, "since_hours": 6, "limit": 3}),
              ("web_search", "c3", {"query": "明日の天気"}),
              ("delegate_to_grok_bot", "c4", {"request": "出張の手配を調べて"}))],
        SPEECH,
    ]
    async with realtime(tmp_path, scripts) as (_, config, client, base, fake, http, helper):
        async with connected(client, base, config) as device:
            messages = await talk(device)
        outputs = fake.events("conversation.item.create")
        assert [o["item"]["call_id"] for o in outputs] == ["c1", "c2", "c3", "c4"]
        assert all(o["item"]["type"] == "function_call_output" for o in outputs)
        schedule, mail, search, task = tool_outputs(fake)
        assert schedule["events"][0]["title"] == "会議"
        assert mail["messages"][0]["subject"] == "資料の件"
        assert search == {"summary": "明日は晴れです。"}
        assert task == {"status": "accepted"}
        received = [e["type"] for e in fake.received]
        assert received[-5:] == ["conversation.item.create"] * 4 + ["response.create"]
        assert received.count("response.create") == 2

        calls = helper_calls(helper)
        assert ["schedule", "--from", "2026-11-22", "--to", "2026-11-23"] in calls
        assert ["mail", "--since-hours", "6", "--limit", "3"] in calls
        headers, body = http.search[0]
        assert headers["Authorization"] == "Bearer " + config.openai_api_key
        assert body["model"] == "gpt-6.2-astra" and body["tools"] == [{"type": "web_search"}]
        assert "明日の天気" in body["input"]
        headers, body = http.tasks[0]
        assert headers["Authorization"] == "Bearer " + config.task_webhook_key == headers["X-Automation-Key"].join(("Bearer ", ""))
        assert body["v"] == 1 and body["type"] == "task" and body["text"] == "出張の手配を調べて"
        assert body["request_id"] and body["created_at"] and set(body) == {"v", "type", "request_id", "text", "created_at"}
    assert any(isinstance(m, bytes) for m in messages)


async def test_delegate_not_configured_and_failed(tmp_path):
    scripts = [[done(("delegate_to_grok_bot", "c1", {"request": "調べて"}))], SPEECH]
    async with realtime(tmp_path, scripts, task=False) as (_, config, client, base, fake, http, _):
        async with connected(client, base, config) as device:
            await talk(device)
        assert tool_outputs(fake) == [{"status": "not_configured"}]
        assert not http.tasks
    scripts = [[done(("delegate_to_grok_bot", "c1", {"request": "調べて"}))], SPEECH]
    async with realtime(tmp_path, scripts, http=FakeHttp(status=500)) as (_, config, client, base, fake, http, _):
        async with connected(client, base, config) as device:
            await talk(device)
        assert tool_outputs(fake) == [{"status": "failed"}]


@pytest.mark.parametrize("code, error", [(3, "permission_denied"), (4, "mail_not_running"), (1, "unavailable"), (5, "unavailable")])
async def test_helper_exit_codes(tmp_path, code, error):
    scripts = [[done(("get_schedule", "c1", {}), ("get_mail", "c2", {}))], SPEECH]
    helper = make_helper(tmp_path / "context", exit_code=code)
    async with realtime(tmp_path, scripts, helper=helper) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            await talk(device)
        assert tool_outputs(fake) == [{"error": error}] * 2


async def test_tool_timeout_and_unknown_tool(tmp_path, monkeypatch):
    from grokwatch_gateway import tools

    monkeypatch.setitem(tools.TIMEOUTS, "get_schedule", 0.2)
    monkeypatch.setitem(tools.TIMEOUTS, "get_mail", 0.2)
    helper = make_helper(tmp_path / "context", delay=30)
    scripts = [[done(("get_schedule", "c1", {}), ("nope", "c2", {}))], SPEECH]
    async with realtime(tmp_path, scripts, helper=helper) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            await talk(device)
        assert tool_outputs(fake) == [{"error": "timeout"}, {"error": "unknown_tool"}]


async def test_schedule_cache_and_refresh(tmp_path):
    scripts = [[done(("get_schedule", "c1", {}))], SPEECH]
    async with realtime(tmp_path, scripts) as (_, config, client, base, fake, _, helper):
        async with connected(client, base, config) as device:
            await device.start()
            await eventually(lambda: len(helper_calls(helper)) >= 2)
            await device.stop()
            await device.idle()
        calls = helper_calls(helper)
        assert [c[0] for c in calls] == ["schedule", "mail"]  # background refresh; the tool call hit the cache
        assert calls[1] == ["mail", "--since-hours", "24", "--limit", "10", "--unread-only"]
        assert tool_outputs(fake)[0]["events"][0]["title"] == "会議"


async def test_session_reused_then_closed_after_idle(tmp_path):
    async with realtime(tmp_path, realtime_idle=0.3) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            await talk(device)
            await talk(device)
            assert fake.connections == 1
            assert len(fake.events("session.update")) == 2  # second one only refreshes the instructions
            assert "tools" not in fake.events("session.update")[1]["session"]
            await eventually(lambda: fake.open == 0)
            await talk(device)
            assert fake.connections == 2


async def test_connect_failure_falls_back_to_webhook_path(tmp_path):
    bridge = FallbackBridge()
    async with realtime(tmp_path, bridge=bridge, realtime_url="ws://127.0.0.1:1/v1/realtime") as (
        _, config, client, base, _, _, _,
    ):
        async with connected(client, base, config) as device:
            messages = await talk(device)
    assert bridge.texts == ["試験の発話です"]
    assert [m["state"] for m in messages if isinstance(m, dict) and m["type"] == "state"] == ["speaking", "idle"]
    assert any(isinstance(m, bytes) for m in messages)


async def test_connect_failure_without_webhook_plays_canned_audio(tmp_path):
    async with realtime(tmp_path, realtime_url="ws://127.0.0.1:1/v1/realtime") as (_, config, client, base, _, _, _):
        async with connected(client, base, config) as device:
            messages = await talk(device)
    assert {"type": "error", "code": "bridge_unavailable", "retryable": True} in messages
    assert {"type": "tts_start", "sample_rate": 16000, "emotion": "sad"} in messages
    assert any(isinstance(m, bytes) for m in messages)


async def test_drop_before_audio_falls_back(tmp_path):
    bridge = FallbackBridge()
    async with realtime(tmp_path, [["close"]], bridge=bridge) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            messages = await talk(device)
            assert bridge.texts == ["試験の発話です"]
            assert any(isinstance(m, bytes) for m in messages)
            await talk(device)  # the next turn reconnects
            assert fake.connections == 2


async def test_error_event_before_audio_falls_back(tmp_path):
    bridge = FallbackBridge()
    scripts = [[{"type": "error", "error": {"code": "server_error"}}]]
    async with realtime(tmp_path, scripts, bridge=bridge) as (_, config, client, base, _, _, _):
        async with connected(client, base, config) as device:
            await talk(device)
    assert bridge.texts == ["試験の発話です"]


async def test_drop_mid_speech_ends_tts_without_fallback(tmp_path):
    bridge = FallbackBridge()
    async with realtime(tmp_path, [[delta(), "close"]], bridge=bridge) as (_, config, client, base, _, _, _):
        async with connected(client, base, config) as device:
            messages = await talk(device)
    assert not bridge.texts
    names = kinds(messages)
    assert names.count("tts_start") == 1 and names[-2:] == ["tts_end", "state"]
    assert messages[-1] == {"type": "state", "state": "idle"}
    assert sum(isinstance(m, bytes) for m in messages) == 5


async def test_silent_server_times_out_to_fallback(tmp_path):
    bridge = FallbackBridge()
    async with realtime(tmp_path, [[30]], bridge=bridge, realtime_response_timeout=0.3) as (_, config, client, base, _, _, _):
        async with connected(client, base, config) as device:
            await talk(device)
    assert bridge.texts == ["試験の発話です"]


async def test_cancel_while_listening_clears_buffer(tmp_path):
    async with realtime(tmp_path) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            await device.send("listen_start", session=1)
            assert await device.receive() == {"type": "state", "state": "listening", "session": 1}
            for _ in range(3):
                await device.ws.send_bytes(b"\0" * 640)
            await eventually(lambda: len(fake.events("input_audio_buffer.append")) == 3)
            await device.send("cancel", session=1)
            assert await device.receive() == {"type": "state", "state": "idle", "session": 1}
            await eventually(lambda: len(fake.events("input_audio_buffer.clear")) >= 2)
            assert not fake.events("input_audio_buffer.commit")


async def test_short_utterance_is_no_speech(tmp_path):
    async with realtime(tmp_path) as (_, config, client, base, fake, _, _):
        async with connected(client, base, config) as device:
            messages = await talk(device, frames=3)
        assert not fake.events("response.create")
    assert {"type": "error", "code": "no_speech", "retryable": True} in messages


async def test_healthz_and_secrets_not_logged(tmp_path, capsys):
    scripts = [[done(("get_schedule", "c1", {}), ("get_mail", "c2", {}), ("web_search", "c3", {"query": "秘密の検索語"}),
                     ("delegate_to_grok_bot", "c4", {"request": "秘密の依頼"}))], SPEECH]
    async with realtime(tmp_path, scripts) as (_, config, client, base, fake, _, _):
        async with client.get(fake.reply_base + "/healthz") as response:
            body = await response.json()
        assert body["bridge"] == {"name": "realtime", "available": True} and body["version"] == "1.2.1"
        assert config.openai_api_key not in json.dumps(body)
        async with connected(client, base, config) as device:
            await talk(device)
        await eventually(lambda: fake.open == 1)
    out = capsys.readouterr().out
    for secret in (config.openai_api_key, config.task_webhook_key, config.task_webhook_url, "会議", "資料の件",
                   "明日は晴れ", "秘密の検索語", "秘密の依頼"):
        assert secret not in out
    events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    tools = [e for e in events if e["event"] == "tool_call"]
    assert {e["tool"] for e in tools} == {"get_schedule", "get_mail", "web_search", "delegate_to_grok_bot"}
    assert all("latency_ms" in e for e in tools)
    assert any(e["event"] == "realtime_first_audio" for e in events)


async def test_redaction_list_includes_realtime_secrets(tmp_path, capsys):
    from grokwatch_gateway.__main__ import create_gateway
    from grokwatch_gateway.config import Config

    key, task_key = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    config = Config(device_token=secrets.token_urlsafe(32), bridge_name="realtime", openai_api_key=key,
                    task_webhook_key=task_key, task_webhook_url="https://example.invalid/" + task_key)
    gateway_ = create_gateway(config)
    for value in (key, task_key):
        gateway_.devices.log("probe", code=value)
    out = capsys.readouterr().out
    assert key not in out and task_key not in out and out.count("***") >= 2


def test_config_from_env():
    from grokwatch_gateway.config import Config

    env = {"GROKWATCH_DEVICE_TOKEN": secrets.token_urlsafe(32), "GROKWATCH_ALLOW_ENV_SECRETS": "1",
           "GROKWATCH_BRIDGE": "realtime", "GROKWATCH_OPENAI_API_KEY": "sk-unique-value", "HOME": "/srv/owner"}
    with pytest.raises(ValueError):
        Config.from_env({k: v for k, v in env.items() if k != "GROKWATCH_OPENAI_API_KEY"})
    config = Config.from_env(env)
    assert (config.realtime_model, config.realtime_voice, config.search_model) == ("gpt-realtime-2.1", "marin", "gpt-6.2-astra")
    assert config.context_bin == "/srv/owner/.local/share/GrokWatch/bin/grokwatch-context"
    assert config.realtime_url == "wss://api.openai.com/v1/realtime" and config.task_webhook_url == ""
    assert "sk-unique-value" not in repr(config)
    config = Config.from_env(env | {"GROKWATCH_REALTIME_MODEL": "m", "GROKWATCH_REALTIME_VOICE": "v",
                                    "GROKWATCH_SEARCH_MODEL": "s", "GROKWATCH_CONTEXT_BIN": "/b"})
    assert (config.realtime_model, config.realtime_voice, config.search_model, config.context_bin) == ("m", "v", "s", "/b")
    for bad in ({"GROKWATCH_REALTIME_URL": "ws://example.com/x"}, {"GROKWATCH_RESPONSES_URL": "http://example.com/x"},
                {"GROKWATCH_TASK_WEBHOOK_URL": "http://example.com/x", "GROKWATCH_TASK_WEBHOOK_KEY": "k"},
                {"GROKWATCH_TASK_WEBHOOK_KEY": "k"}):
        with pytest.raises(ValueError):
            Config.from_env(env | bad)



def test_slow_helper_fills_cache_after_tool_timeout(tmp_path, monkeypatch):
    """A tool call that times out leaves the shared helper run going; its result is cached for the next call."""
    import asyncio as _asyncio
    import json as _json
    from types import SimpleNamespace
    from grokwatch_gateway import tools as tools_module
    from tests.fixtures.realtime_fake import helper_calls, make_helper

    helper = make_helper(tmp_path / "ctx", delay=0.4)
    monkeypatch.setitem(tools_module.TIMEOUTS, "get_mail", 0.1)
    config = SimpleNamespace(context_bin=str(helper))

    async def scenario():
        tools = tools_module.Tools(config, lambda *a, **k: None, _asyncio.get_running_loop().time)
        first = _json.loads(await tools.call("get_mail", "{}"))
        await _asyncio.sleep(0.8)
        second = _json.loads(await tools.call("get_mail", "{}"))
        return first, second

    first, second = _asyncio.run(scenario())
    assert first == {"error": "timeout"}
    assert second["messages"][0]["subject"] == "資料の件"
    assert len(helper_calls(helper)) == 1


def test_server_error_before_turn_is_logged():
    """An error event outside a turn (e.g. a rejected session.update) is logged with type/code/param only."""
    from types import SimpleNamespace
    from grokwatch_gateway.realtime import RealtimeSession

    logged = []
    session = RealtimeSession(SimpleNamespace(), lambda event, **kw: logged.append((event, kw)), lambda: 0,
                              tools=object())
    session.log_server_error({"type": "error", "error": {"type": "invalid_request_error",
                                                          "code": "unknown_parameter", "param": "session.x",
                                                          "message": "secret text"}})
    assert logged == [("realtime_server_error", {"level": "warning",
                                                 "code": "invalid_request_error:unknown_parameter:session.x"})]
