import asyncio
import secrets

import pytest

from fake_device import reconnect
from support import Device, connected, eventually, gateway, post


@pytest.fixture(autouse=True)
async def deadline():
    async with asyncio.timeout(10):
        yield


@pytest.mark.parametrize("mode, kwargs, code, expected_states", [
    ("post_reply", {}, None, ["speaking", "idle"]),
    ("post_reply", {"stt_text": ""}, "no_speech", ["idle"]),
    ("post_reply", {"stt_fail": True}, "stt_failed", ["error", "speaking", "idle"]),
    ("fail", {}, "bridge_unavailable", ["error", "speaking", "idle"]),
    ("silent", {"reply_timeout": 1}, "bridge_timeout", ["error", "speaking", "idle"]),
    ("post_reply", {"mock_variant": "duplicate"}, None, ["speaking", "idle"]),
    ("post_reply", {"mock_variant": "tampered", "reply_timeout": 0.3},
     "bridge_timeout", ["error", "speaking", "idle"]),
])
async def test_roundtrip_modes(mode, kwargs, code, expected_states, capsys):
    from grokwatch_gateway.audio import MockTts
    from grokwatch_gateway.canned import CANNED_TEXT

    async with gateway(bridge_name="mock", mock_mode=mode, mock_text="試験返事", **kwargs) as (
        app, config, client, base, reply_base,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            messages = await device.idle()
            states = [m["state"] for m in messages if isinstance(m, dict) and m["type"] == "state"]
            assert states == expected_states
            assert [m["code"] for m in messages if isinstance(m, dict) and m["type"] == "error"] == (
                [code] if code else []
            )
            request = app.bridge.last_request
            if code == "no_speech":
                assert request is None and len(messages) == 2
                return
            frames = [m for m in messages if isinstance(m, bytes)]
            start = messages.index({"type": "tts_start", "sample_rate": 16000})
            end = messages.index({"type": "tts_end"})
            assert frames == messages[start + 1:end] and frames
            assert messages.count({"type": "tts_start", "sample_rate": 16000}) == 1
            assert all(len(frame) == 640 for frame in frames)
            audio = await MockTts()(CANNED_TEXT[code] if code else "試験返事")
            assert b"".join(frames) == audio + b"\0" * (-len(audio) % 640)
            if mode == "silent":
                assert (await post(client, reply_base, request.request_id, request.reply_token))[0] == 410
            if kwargs.get("mock_variant") == "tampered":
                assert app.bridge.post_results == [(401, None)]
            elif kwargs.get("mock_variant") == "duplicate":
                assert app.bridge.post_results == [(200, "accepted"), (200, "duplicate")]
            logs = capsys.readouterr().out
            assert config.device_token not in logs
            if request:
                assert request.reply_token not in logs


async def test_delayed_reply_stays_thinking():
    async with gateway(bridge_name="mock", mock_mode="post_reply", mock_delay=3) as (
        _, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(2.8):
                    await device.receive()
            assert (await device.receive())["state"] == "speaking"
            await device.idle()


async def test_cancel_then_late_reply_410():
    async with gateway(bridge_name="mock", mock_mode="silent") as (app, config, client, base, reply_base):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            request = await eventually(lambda: app.bridge.last_request)
            await device.send("cancel")
            assert await device.idle() == [{"type": "state", "state": "idle"}]
            assert (await post(client, reply_base, request.request_id, request.reply_token))[0] == 410
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(2):
                    await device.receive()


async def test_cancel_during_speaking_roundtrip():
    async with gateway(bridge_name="mock", mock_mode="post_reply", mock_text="音声" * 70) as (
        _, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            assert (await device.receive())["state"] == "speaking"
            assert (await device.receive())["type"] == "tts_start"
            await device.send("cancel")
            assert {"type": "tts_end"} not in await device.idle()
            await device.send("ping", t=10)
            assert await device.receive() == {"type": "pong", "t": 10}


@pytest.mark.parametrize("auth", [True, False])
async def test_unauthenticated_device(auth):
    async with gateway() as (_, _, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            device = Device(ws)
            if auth:
                await device.hello(secrets.token_urlsafe(32))
                assert await device.receive() == {"type": "auth_error", "code": "bad_token"}
            else:
                await device.send("listen_start")
            assert await device.receive() == (4001 if auth else 4003)


async def test_gateway_restart_reconnect():
    from aiohttp import ClientSession

    async with gateway(bridge_name="mock", mock_mode="silent") as (app, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            old = await eventually(lambda: app.bridge.last_request)
        port = int(base.rsplit(":", 1)[1])
    resumed = asyncio.Event()
    delays = []

    async def pause(seconds):
        delays.append(seconds)
        if delays == [0.01, 0.02, 0.04]:
            resumed.set()
        await asyncio.sleep(seconds)

    async with ClientSession() as client:
        new_token = config.device_token
        trying = asyncio.create_task(reconnect(client, base, new_token, pause))
        try:
            await resumed.wait()
            async with gateway(bridge_name="mock", mock_mode="post_reply", port=port,
                               test_device_token=new_token) as (_, _, _, _, reply_base):
                device = await trying
                try:
                    assert (await post(client, reply_base, old.request_id, old.reply_token))[0] == 404
                    await device.start()
                    await device.stop()
                    assert {"type": "tts_end"} in await device.idle()
                finally:
                    await device.ws.close()
        finally:
            if not trying.done():
                trying.cancel()
                await asyncio.gather(trying, return_exceptions=True)
    assert delays[:3] == [0.01, 0.02, 0.04]


async def test_device_drop_mid_turn_and_health():
    async with gateway(bridge_name="mock", mock_mode="post_reply", mock_delay=0.05) as (
        app, config, client, base, reply_base,
    ):
        async def health(expected):
            async with client.get(reply_base + "/healthz") as response:
                assert response.status == 200
                info = await response.json()
                assert info["status"] == "ok"
                assert info["device_connected"] is expected

        await health(False)
        async with connected(client, base, config) as device:
            await health(True)
            await device.start()
            await device.stop()
            old = await eventually(lambda: app.bridge.last_request)
        await eventually(lambda: not app.device_connected)
        await health(False)
        assert (await post(client, reply_base, old.request_id, old.reply_token))[0] == 410
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            assert {"type": "tts_end"} in await device.idle()
            assert old.session_id != app.bridge.last_request.session_id
