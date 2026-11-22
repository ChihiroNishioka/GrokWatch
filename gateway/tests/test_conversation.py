import asyncio

import pytest
from aiohttp import web

from support import connected, eventually, gateway, post, process_gone, serve


def states(messages):
    return [m["state"] for m in messages if isinstance(m, dict) and m["type"] == "state"]


def audio(messages):
    return b"".join(m for m in messages if isinstance(m, bytes))


async def test_thinking_before_stt_and_no_speech():
    transcribing = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def stt(pcm):
        calls.append(pcm)
        transcribing.set()
        await release.wait()
        return "  "

    async with gateway(stt=stt, bridge_name="mock") as (app, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop(frames=14)
            assert (await device.idle())[0]["code"] == "no_speech"
            assert not calls
            await device.start()
            await device.stop()
            await transcribing.wait()
            assert not release.is_set()
            release.set()
            assert (await device.idle())[0]["code"] == "no_speech"
            assert not app.bridge.last_request


@pytest.mark.parametrize("scenario, code, expected", [
    ("stt", "stt_failed", "うまく聞き取れなかったみたい"),
    ("bridge", "bridge_unavailable", "いま伝書鳩につながらないみたい"),
    ("empty_ok", "reply_error", "ごめん、いまは答えられないみたい"),
    ("error", "reply_error", "ごめん、いまは答えられないみたい"),
    ("error_text", "reply_error", "試験返事"),
    ("declined", None, "試験返事"),
])
async def test_error_and_declined_audio(scenario, code, expected):
    from grokwatch_gateway.audio import SttError

    calls = []

    async def stt(pcm):
        if scenario == "stt":
            raise SttError()
        return "質問"

    async def tts(text):
        calls.append(text)
        return bytes([calls.index(text) + 1]) * 640

    options = dict(bridge_name="mock", mock_mode={"bridge": "fail", "empty_ok": "fixed",
                                                   "error": "fixed"}.get(scenario, "post_reply"),
                   mock_status="error" if scenario.startswith("error") else
                   "declined" if scenario == "declined" else "ok",
                   mock_text="" if scenario in {"error", "empty_ok"} else "試験返事",
                   mock_end=True)
    async with gateway(stt=stt, tts=tts, **options) as (app, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            messages = await device.idle()
            assert states(messages) == (["error"] if code else []) + ["speaking", "idle"]
            if code:
                assert messages[1] == {"type": "error", "code": code, "retryable": True}
            assert audio(messages) == bytes([calls.index(expected) + 1]) * 640
            assert calls.count(expected) == 1
            if scenario == "stt":
                assert not app.bridge.last_request


async def test_webhook_timeout_uses_created_at():

    triggered = asyncio.Event()
    release = asyncio.Event()
    now = [100.0]
    received = []

    async def webhook(request):
        received.append(await request.json())
        triggered.set()
        await release.wait()
        return web.Response()

    fake = web.Application()
    fake.router.add_post("/", webhook)
    async with serve(fake) as hook_url:
        import secrets
        async with gateway(clock=lambda: now[0], reply_timeout=1, webhook_url=hook_url,
                           webhook_allow_loopback_http=True,
                           webhook_key=secrets.token_urlsafe(32)) as (app, config, client, base, _):
            async with connected(client, base, config) as device:
                await device.start()
                await device.stop()
                await triggered.wait()
                now[0] += 1
                try:
                    async with asyncio.timeout(0.4):
                        messages = await device.idle()
                finally:
                    release.set()
                assert messages[1]["code"] == "bridge_timeout"
                assert audio(messages)
                assert app.registry.state(received[0]["request_id"]) == "expired"


@pytest.mark.parametrize("action", ["cancel", "disconnect", "restart_listening"])
async def test_pending_cancelled(action):
    async with gateway(bridge_name="mock", mock_mode="silent") as (app, config, client, base, reply_base):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            request = await eventually(lambda: app.bridge.last_request)
            if action == "disconnect":
                await device.ws.close()
            elif action == "restart_listening":
                await device.start()
            else:
                await device.send("cancel")
                assert await device.idle() == [{"type": "state", "state": "idle"}]
            await eventually(lambda: app.registry.state(request.request_id) == "cancelled")
            assert (await post(client, reply_base, request.request_id, request.reply_token))[0] == 410


@pytest.mark.parametrize("disconnect", [False, True])
async def test_cancel_stops_stt(fake_commands, monkeypatch, disconnect):
    from grokwatch_gateway.audio import WhisperCpp

    monkeypatch.setenv("GW_FIXTURE_WHISPER_CLI_DELAY", "60")
    async with gateway(stt=WhisperCpp(model="fixture"), bridge_name="mock") as (app, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            pid = fake_commands / "whisper-cli.pid"
            await eventually(pid.exists)
            if disconnect:
                await device.ws.close()
                await eventually(lambda: not app.device_connected)
            else:
                await device.send("cancel")
                await device.idle()
            process_gone(pid)
            assert app.bridge.last_request is None


async def test_cancel_during_speaking_stops_audio():
    first_pause = asyncio.Event()

    async def sleep(seconds):
        first_pause.set()
        await asyncio.sleep(60)

    async def tts(text):
        return b"\1" * (640 * 50)

    async with gateway(tts=tts, sleep=sleep, bridge_name="mock", mock_mode="post_reply") as (
        app, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            await first_pause.wait()
            await device.send("cancel")
            async with asyncio.timeout(0.1):
                messages = await device.idle()
            assert len(audio(messages)) == 640 * 10
            assert {"type": "tts_end"} not in messages
            assert app.registry.state(app.bridge.last_request.request_id) == "answered"


async def test_tts_framing_and_pacing(monkeypatch):
    from aiohttp.web import WebSocketResponse

    sent = []
    now = [100.0]
    original_send = WebSocketResponse.send_bytes

    async def send_bytes(ws, data):
        sent.append(now[0])
        now[0] += 0.001
        await original_send(ws, data)

    monkeypatch.setattr(WebSocketResponse, "send_bytes", send_bytes)

    async def tts(text):
        return b"x" * (11 * 640 + 2)

    async def sleep(seconds):
        now[0] += seconds

    async with gateway(tts=tts, sleep=sleep, pace_clock=lambda: now[0], bridge_name="mock") as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            messages = await device.idle()
            assert messages[:2] == [{"type": "state", "state": "speaking"},
                                    {"type": "tts_start", "sample_rate": 16000}]
            assert all(len(m) == 640 for m in messages[2:-2])
            assert audio(messages) == b"x" * (11 * 640 + 2) + b"\0" * 638
            assert sent == pytest.approx([100 + i * 0.001 for i in range(10)] + [100.02, 100.04])
            assert messages[-2] == {"type": "tts_end"}


async def test_tts_failure_and_canned_fallback():
    from grokwatch_gateway.audio import TtsError

    calls = []

    async def tts(text):
        calls.append(text)
        raise TtsError()

    async with gateway(tts=tts, bridge_name="mock") as (_, config, client, base, _):
        assert len(calls) == 4
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            assert await device.idle() == [
                {"type": "state", "state": "error"},
                {"type": "error", "code": "tts_failed", "retryable": True},
                {"type": "state", "state": "idle"},
            ]
    async with gateway(tts=tts, bridge_name="mock", mock_mode="fail") as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            start_count = len(calls)
            for _ in range(2):
                await device.start()
                await device.stop()
                messages = await device.idle()
                assert states(messages) == ["error", "idle"]
                assert not audio(messages)
            assert len(calls) == start_count


async def test_tts_cancel(fake_commands, monkeypatch):
    from grokwatch_gateway.audio import MacosSay

    async with gateway(tts=MacosSay(), bridge_name="mock") as (_, config, client, base, _):
        pid = fake_commands / "say.pid"
        pid.unlink()
        monkeypatch.setenv("GW_FIXTURE_SAY_DELAY", "60")
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            await eventually(pid.exists)
            await device.send("cancel")
            assert await device.idle() == [{"type": "state", "state": "idle"}]
            process_gone(pid)
