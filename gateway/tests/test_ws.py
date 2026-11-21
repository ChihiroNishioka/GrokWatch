import asyncio
import hmac
import secrets

import pytest

from support import Device, connected, eventually, gateway


async def test_hello_ok():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config):
            pass


@pytest.mark.parametrize("version, valid, error, code", [
    (1, False, "bad_token", 4001), (2, True, "unsupported_version", 4000),
])
async def test_auth_failure(version, valid, error, code):
    async with gateway() as (_, config, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            device = Device(ws)
            await device.hello(config.device_token if valid else secrets.token_urlsafe(32), version)
            assert await device.receive() == {"type": "auth_error", "code": error}
            assert await device.receive() == code


@pytest.mark.parametrize("message", ['{"type":"listen_start"}', '{"type":"ping","t":0}', b"\0", "{"])
async def test_pre_auth_messages_close_4003(message):
    async with gateway() as (_, _, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            await (ws.send_bytes(message) if isinstance(message, bytes) else ws.send_str(message))
            assert await Device(ws).receive() == 4003


async def test_hello_timeout_closes_4002():
    async with gateway(hello_timeout=0.02) as (_, _, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            assert await Device(ws).receive() == 4002


def test_startup_rejects_short_token():
    from grokwatch_gateway.config import Config

    for size in (0, 31):
        with pytest.raises(ValueError):
            Config(device_token="a" * size)
    Config(device_token="a" * 32)


async def test_token_compare_is_constant_time(monkeypatch):
    compared = []
    original = hmac.compare_digest

    def capture(left, right):
        compared.append((left, right))
        return original(left, right)

    monkeypatch.setattr(hmac, "compare_digest", capture)
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config):
            value = config.device_token.encode()
            assert (value, value) in compared


async def test_new_connection_replaces_old():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config) as first:
            async with client.ws_connect(base + "/v1/ws") as ws:
                bad = Device(ws)
                await bad.hello(secrets.token_urlsafe(32))
                assert (await bad.receive())["code"] == "bad_token"
                assert await bad.receive() == 4001
            await first.send("ping", t=1)
            assert await first.receive() == {"type": "pong", "t": 1}
            async with connected(client, base, config):
                assert await first.receive() == 4004


async def test_idle_connection_closed_4005():
    async with gateway(bridge_name="mock", mock_mode="silent", idle_timeout=0.2) as (
        app, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            request = await eventually(lambda: app.bridge.last_request)
            assert await device.receive() == 4005
            await eventually(lambda: app.registry.state(request.request_id) == "cancelled")


async def test_ping_unknown_and_bad_message():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.send("unknown")
            await device.ws.send_str("{")
            assert await device.receive() == {"type": "error", "code": "bad_message", "retryable": False}
            await device.send("ping", t=123)
            assert await device.receive() == {"type": "pong", "t": 123}


async def test_oversized_text_frame():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            prefix = '{"type":"ping","t":1,"pad":"'
            message = prefix + "x" * (4096 - len(prefix) - 2) + '"}'
            await device.ws.send_str(message)
            assert (await device.receive())["type"] == "pong"
            for size in (4097, 4159):
                await device.ws.send_str(message.ljust(size))
                assert (await device.receive())["code"] == "bad_message"


async def test_frames_outside_listening_and_bad_frame_once():
    captured = []

    async def transcribe(pcm):
        captured.append(pcm)
        return ""

    async with gateway(stt=transcribe) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.ws.send_bytes(b"x" * 640)
            await device.start()
            await device.ws.send_bytes(b"x" * 639)
            await device.ws.send_bytes(b"x" * 641)
            assert await device.receive() == {"type": "error", "code": "bad_frame", "retryable": False}
            await device.stop()
            await device.ws.send_bytes(b"x" * 640)
            assert await device.idle() == [
                {"type": "error", "code": "no_speech", "retryable": True},
                {"type": "state", "state": "idle"},
            ]
            assert captured == [b"\0" * 640 * 15]


async def test_listen_max_750_frames():
    captured = []

    async def transcribe(pcm):
        captured.append(len(pcm))
        return ""

    async with gateway(stt=transcribe) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.start()
            for _ in range(749):
                await device.ws.send_bytes(b"\0" * 640)
            await device.send("ping", t=749)
            assert (await device.receive())["type"] == "pong"
            await device.ws.send_bytes(b"\0" * 640)
            assert (await device.receive())["state"] == "thinking"
            await device.ws.send_bytes(b"\0" * 640)
            await device.send("listen_stop")
            await device.idle()
            assert captured == [750 * 640]


async def test_replace_while_old_connection_disconnects_during_cleanup():
    started = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def stt(pcm):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cleaning.set()
            await release.wait()
            finished.set()

    async with gateway(stt=stt) as (_, config, client, base, _):
        async with connected(client, base, config) as first:
            await first.start()
            await first.stop()
            await started.wait()
            async with client.ws_connect(base + "/v1/ws") as replacement:
                second = Device(replacement)
                await second.hello(config.device_token)
                try:
                    async with asyncio.timeout(1):
                        await cleaning.wait()
                        await first.ws.close()
                        # Let the old connection process the close while STT is still cleaning up.
                        await asyncio.sleep(0.02)
                        release.set()
                        assert await second.receive() == {"type": "hello_ok", "v": 1}
                        assert finished.is_set()
                finally:
                    release.set()


@pytest.mark.parametrize("authenticated", [False, True])
async def test_parser_oversize_uses_v1_error_path(authenticated):
    async with gateway() as (_, config, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            device = Device(ws)
            if authenticated:
                await device.hello(config.device_token)
                assert (await device.receive())["type"] == "hello_ok"
            await ws.send_bytes(b"x" * 4_160)
            if authenticated:
                assert (await device.receive())["code"] == "bad_message"
            assert await device.receive() == 4003


async def test_ws_admission_limit_includes_pending_hello():
    from contextlib import AsyncExitStack
    from aiohttp import WSServerHandshakeError

    async with gateway() as (_, config, client, base, _):
        async with AsyncExitStack() as sockets:
            for _ in range(4):
                await sockets.enter_async_context(client.ws_connect(base + "/v1/ws"))
            with pytest.raises(WSServerHandshakeError) as error:
                await client.ws_connect(base + "/v1/ws")
            assert error.value.status == 503
        async with connected(client, base, config):
            pass


async def test_cancel_ack_echoes_session_number():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.send("listen_start", session=1)
            assert (await device.receive())["state"] == "listening"
            await device.send("cancel", session=1)
            await device.send("listen_start", session=2)
            assert await device.receive() == {"type": "state", "state": "idle", "session": 1}
            assert (await device.receive())["state"] == "listening"


async def test_turn_state_and_error_echo_device_session_number():
    async with gateway() as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.send("listen_start", session=17)
            assert await device.receive() == {"type": "state", "state": "listening", "session": 17}
            await device.send("listen_stop")
            assert await device.receive() == {"type": "state", "state": "thinking", "session": 17}
            messages = []
            async with asyncio.timeout(3):
                while True:
                    message = await device.receive()
                    messages.append(message)
                    if message.get("type") == "state" and message.get("state") == "idle":
                        break
            assert messages == [
                {"type": "error", "code": "no_speech", "retryable": True, "session": 17},
                {"type": "state", "state": "idle", "session": 17},
            ]


async def test_error_and_speaking_states_echo_device_session_number():
    async def transcribe(pcm):
        return "質問"

    async def speak(text):
        return b"\x01" * 640

    async with gateway(stt=transcribe, tts=speak, bridge_name="mock", mock_mode="post_reply",
                       mock_status="error", mock_text="返事") as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.send("listen_start", session=18)
            assert await device.receive() == {"type": "state", "state": "listening", "session": 18}
            for _ in range(15):
                await device.ws.send_bytes(b"\0" * 640)
            await device.send("listen_stop")
            messages = []
            async with asyncio.timeout(5):
                while True:
                    message = await device.receive()
                    messages.append(message)
                    if message == {"type": "state", "state": "idle", "session": 18}:
                        break
            states = [message for message in messages
                      if isinstance(message, dict) and message.get("type") == "state"]
            errors = [message for message in messages
                      if isinstance(message, dict) and message.get("type") == "error"]
            assert states == [
                {"type": "state", "state": "thinking", "session": 18},
                {"type": "state", "state": "error", "session": 18},
                {"type": "state", "state": "speaking", "session": 18},
                {"type": "state", "state": "idle", "session": 18},
            ]
            assert errors == [
                {"type": "error", "code": "reply_error", "retryable": True, "session": 18},
            ]


async def test_cancel_waiter_propagates_its_own_cancellation():
    running = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def stt(pcm):
        running.set()
        try:
            await asyncio.Future()
        finally:
            cleaning.set()
            await release.wait()
            finished.set()

    async with gateway(stt=stt) as (app, config, client, base, _):
        async with connected(client, base, config) as device:
            server_session = app.devices.active
            await device.start()
            await device.stop()
            await running.wait()
            waiter = asyncio.create_task(server_session.cancel())
            try:
                await cleaning.wait()
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter
            finally:
                release.set()
            await server_session.cancel()
            assert finished.is_set()
