import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
from aiohttp import web
import pytest


@pytest.fixture(autouse=True)
def fake_commands(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixtures = Path(__file__).parent
    for command in ("gbot", "say", "security", "whisper-cli"):
        (bin_dir / command).symlink_to(fixtures / "fake_command.sh")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("GW_FIXTURE_SCRIPT", str(fixtures / "fake_command.py"))
    monkeypatch.setenv("GW_FIXTURE_PYTHON", sys.executable)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setenv("GW_FIXTURE_DIR", str(output_dir))
    return output_dir


@asynccontextmanager
async def serve(app, port=0):
    runner = web.AppRunner(app, access_log=None, shutdown_timeout=0.2)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()


def reply_body(request_id, **fields):
    return json.dumps(dict(v=1, request_id=request_id, status="ok", text="返事") | fields,
                      ensure_ascii=False, separators=(",", ":")).encode()


def reply_headers(request_id, key, body, timestamp=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = hmac.new(key.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return {
        "Content-Type": "application/json",
        "X-GrokWatch-Request-Id": request_id,
        "X-GrokWatch-Timestamp": timestamp,
        "X-GrokWatch-Signature": "sha256=" + signature.hexdigest(),
    }


async def post(client, base, request_id, key, body=None, timestamp=None):
    if body is None:
        body = reply_body(request_id)
    async with client.post(base + "/v1/reply", data=body,
                           headers=reply_headers(request_id, key, body, timestamp)) as response:
        return response.status, await response.json() if response.status == 200 else None


async def eventually(predicate, timeout=2):
    async with asyncio.timeout(timeout):
        while not (result := predicate()):
            await asyncio.sleep(0.001)
        return result


def process_gone(path):
    pid = int(path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@asynccontextmanager
async def gateway(*, bridge=None, stt=None, tts=None, clock=time.time, sleep=asyncio.sleep, pace_clock=time.monotonic,
                  port=0, test_device_token=None, **settings):
    from grokwatch_gateway.__main__ import create_gateway
    from grokwatch_gateway.config import Config

    config = Config(device_token=test_device_token or secrets.token_urlsafe(32), gateway_host="127.0.0.1",
                    gateway_port=port, reply_port=0, **settings)
    instances = create_gateway(config, stt=stt, tts=tts, bridge=bridge, clock=clock, sleep=sleep, pace_clock=pace_clock)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as client:
        async with serve(instances.reply_app) as reply_base:
            instances.set_reply_url(reply_base + "/v1/reply")
            async with serve(instances.ws_app, port) as ws_base:
                yield instances, config, client, ws_base, reply_base


class Device:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, kind, **fields):
        await self.ws.send_json(dict(type=kind, **fields))

    async def hello(self, token, version=1):
        await self.send("hello", v=version, token=token, fw="0.1.0")

    async def receive(self):
        msg = await self.ws.receive(timeout=3)
        if msg.type == aiohttp.WSMsgType.TEXT:
            return msg.json()
        return msg.data

    async def start(self):
        await self.send("listen_start")
        assert await self.receive() == {"type": "state", "state": "listening"}

    async def stop(self, frames=15, pcm=b"\0" * 640):
        for _ in range(frames):
            await self.ws.send_bytes(pcm)
        await self.send("listen_stop")
        assert await self.receive() == {"type": "state", "state": "thinking"}

    async def until(self, expected):
        messages = []
        async with asyncio.timeout(5):
            while True:
                msg = await self.receive()
                messages.append(msg)
                if msg == expected:
                    return messages
                assert isinstance(msg, (dict, bytes)), messages

    async def idle(self):
        return await self.until({"type": "state", "state": "idle"})


@asynccontextmanager
async def connected(client, ws_base, config):
    async with client.ws_connect(ws_base + "/v1/ws") as ws:
        device = Device(ws)
        await device.hello(config.device_token)
        assert await device.receive() == {"type": "hello_ok", "v": 1}
        yield device
