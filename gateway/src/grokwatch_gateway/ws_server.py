import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import hmac

from aiohttp import WSMsgType, web
from grokwatch_bridge.contract import Session

from .conversation import Conversation
from .protocol import FRAME_BYTES, MAX_FRAMES, decode


_CLOSED = {WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR}


class DeviceSession:
    def __init__(self, server, ws):
        self.server = server
        self.ws = ws
        self.conversation = Conversation(ws, stt=server.stt, tts=server.tts, bridge=server.bridge,
                                         canned=server.canned, log=server.log,
                                         sleep=server.sleep, clock=server.clock)
        self.session = None
        self.capture = None
        self.task = None
        self.bad_frame = False

    async def cancel(self):
        self.capture = None
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError, ConnectionError):
                await self.task
            self.task = None

    async def start(self):
        await self.cancel()
        self.session = self.server.next_session()
        self.capture = bytearray()
        self.bad_frame = False
        await self.conversation.state("listening")

    async def stop(self):
        if self.capture is None:
            return
        pcm = bytes(self.capture)
        self.capture = None
        await self.conversation.state("thinking")
        self.task = asyncio.create_task(self.conversation.run(pcm, self.session))

    async def handle(self, frame):
        if frame.type == WSMsgType.BINARY:
            if self.capture is None:
                return
            if len(frame.data) != FRAME_BYTES:
                if not self.bad_frame:
                    self.bad_frame = True
                    await self.conversation.error("bad_frame", retryable=False)
                return
            self.capture.extend(frame.data)
            if len(self.capture) == FRAME_BYTES * MAX_FRAMES:
                await self.stop()
            return

        if frame.type == WSMsgType.PING:
            await self.ws.pong(frame.data)
            return
        if frame.type == WSMsgType.PONG:
            return
        if (data := decode(frame)) is None:
            await self.conversation.error("bad_message", retryable=False)
            return
        match data["type"]:
            case "listen_start":
                await self.start()
            case "listen_stop":
                await self.stop()
            case "cancel":
                await self.cancel()
                await self.conversation.state("idle")
            case "ping":
                await self.ws.send_json({"type": "pong", "t": data["t"]})
            case "pong" | "error":
                pass
            case _:
                self.server.log("protocol", code="unknown_type")


class WebSocketServer:
    def __init__(self, config, stt, tts, bridge, canned, log, clock, sleep):
        self.config = config
        self.stt = stt
        self.tts = tts
        self.bridge = bridge
        self.canned = canned
        self.log = log
        self.clock = clock
        self.sleep = sleep
        self.active = None
        self.lock = asyncio.Lock()
        self.day = None
        self.sequence = 0

    def next_session(self):
        day = datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y%m%d")
        if day != self.day:
            self.day, self.sequence = day, 0
        self.sequence += 1
        return Session(f"s-{day}-{self.sequence:03d}")

    async def authenticate(self, ws):
        try:
            frame = await ws.receive(timeout=self.config.hello_timeout)
        except TimeoutError:
            await ws.close(code=4002)
            return False
        if frame.type in _CLOSED:
            return False
        data = decode(frame)
        if data is None or data["type"] != "hello":
            await ws.close(code=4003)
            return False

        if data["v"] != 1:
            reason, code = "unsupported_version", 4000
        elif not hmac.compare_digest(data["token"].encode(), self.config.device_token.encode()):
            reason, code = "bad_token", 4001
        else:
            return True
        self.log("authentication_failed", code=reason)
        await ws.send_json({"type": "auth_error", "code": reason})
        await ws.close(code=code)
        return False

    async def handle(self, request):
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        if not await self.authenticate(ws):
            return ws
        device = DeviceSession(self, ws)
        try:
            async with self.lock:
                if old := self.active:
                    await old.cancel()
                    await old.ws.close(code=4004)
                self.active = device
                await ws.send_json({"type": "hello_ok", "v": 1})
            while True:
                try:
                    frame = await ws.receive(timeout=self.config.idle_timeout)
                except TimeoutError:
                    await device.cancel()
                    await ws.close(code=4005)
                    break
                if frame.type in _CLOSED or self.active is not device:
                    break
                await device.handle(frame)
        finally:
            await device.cancel()
            if self.active is device:
                self.active = None
        return ws

    async def shutdown(self, app):
        if device := self.active:
            await device.cancel()
            await device.ws.close()
