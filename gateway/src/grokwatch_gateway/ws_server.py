import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import hmac

from aiohttp import WSCloseCode, WSMsgType, web
from grokwatch_bridge.contract import Session

from .conversation import Conversation, ConversationTurn
from .audio import SttError
from .protocol import FRAME_BYTES, MAX_FRAMES, MAX_TEXT_BYTES, MIN_FRAMES, decode
from .wake import compile_pattern, is_wake


MAX_WS_MESSAGE_BYTES = MAX_TEXT_BYTES + 64
MAX_WAKE_FRAMES = 125


class DeviceSocket(web.WebSocketResponse):
    authenticated = False

    async def close(self, *, code=WSCloseCode.OK, message=b"", drain=True):
        if code == WSCloseCode.MESSAGE_TOO_BIG:
            if self.authenticated:
                await self.send_json({"type": "error", "code": "bad_message", "retryable": False})
            code, drain = 4003, False
        elif code == WSCloseCode.INVALID_TEXT and not self.authenticated:
            code, drain = 4003, False
        return await super().close(code=code, message=message, drain=drain)


_CLOSED = {WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR}


class DeviceSession:
    def __init__(self, server, ws):
        self.server = server
        self.ws = ws
        self.conversation = Conversation(ws, stt=server.stt, tts=server.tts, bridge=server.bridge,
                                         canned=server.canned, log=server.log,
                                         sleep=server.sleep, clock=server.clock, pace_clock=server.pace_clock)
        self.turn = None
        self.capture = None
        self.task = None
        self.cleanup = None
        self.retired = False
        self.bad_frame = False
        self.wake_capture = None
        self.wake_seq = None
        self.wake_task = None
        self.wake_cleanup = None

    @staticmethod
    async def finish_cancel(task):
        task.cancel()
        with suppress(asyncio.CancelledError, ConnectionError):
            await task

    async def cancel_wake(self):
        self.wake_capture = None
        if self.wake_task is not None:
            self.wake_cleanup = asyncio.create_task(self.finish_cancel(self.wake_task))
            self.wake_task = None
        if self.wake_cleanup is not None:
            await asyncio.shield(self.wake_cleanup)

    async def cancel(self):
        self.capture = None
        self.wake_capture = None
        wake = asyncio.create_task(self.cancel_wake())
        if self.task is not None:
            self.cleanup = asyncio.create_task(self.finish_cancel(self.task))
            self.task = None
        try:
            if self.cleanup is not None:
                await asyncio.shield(self.cleanup)
            if self.server.realtime is not None:
                await asyncio.shield(self.server.realtime.discard())
        finally:
            await asyncio.shield(wake)

    async def wake_start(self, seq):
        if self.capture is not None:
            return
        await self.cancel_wake()
        if self.retired:
            return
        self.wake_seq = seq
        self.wake_capture = bytearray()

    async def wake_stop(self, seq):
        if self.wake_capture is None or seq != self.wake_seq:
            return
        pcm = bytes(self.wake_capture)
        self.wake_capture = None
        self.wake_task = asyncio.create_task(self.wake_check(seq, pcm, self.task is not None and not self.task.done()))

    async def wake_check(self, seq, pcm, busy):
        started = self.server.clock()
        frames = len(pcm) // FRAME_BYTES
        hit, text = False, None
        if not busy and frames >= MIN_FRAMES:
            try:
                text = await self.server.wake_stt(pcm)
                hit = is_wake(text, self.server.wake_pattern)
            except SttError:
                text = None
        self.server.log("wake_check", hit=hit, frames=frames, text=text,
                        latency_ms=max(0, round((self.server.clock() - started) * 1000)))
        if not self.retired:
            await self.ws.send_json({"type": "wake", "seq": seq, "hit": hit})

    async def start(self, number):
        await self.cancel()
        if self.retired:
            return
        self.turn = ConversationTurn(number, self.server.next_session())
        self.capture = bytearray()
        self.bad_frame = False
        if self.server.realtime is not None:
            await self.server.realtime.begin()
        await self.conversation.state("listening", self.turn)

    async def stop(self):
        if self.capture is None:
            return
        pcm = bytes(self.capture)
        self.capture = None
        turn = self.turn
        await self.conversation.state("thinking", turn)
        if not self.retired:
            if self.server.realtime is not None:
                run = self.server.realtime.run(self.conversation, pcm, turn)
            else:
                run = self.conversation.run(pcm, turn)
            self.task = asyncio.create_task(run)

    async def handle(self, frame):
        if frame.type == WSMsgType.BINARY:
            if self.capture is None:
                if self.wake_capture is not None and len(frame.data) == FRAME_BYTES \
                        and len(self.wake_capture) < FRAME_BYTES * MAX_WAKE_FRAMES:
                    self.wake_capture.extend(frame.data)
                return
            if len(frame.data) != FRAME_BYTES:
                if not self.bad_frame:
                    self.bad_frame = True
                    await self.conversation.error("bad_frame", retryable=False, turn=self.turn)
                return
            self.capture.extend(frame.data)
            if self.server.realtime is not None:
                await self.server.realtime.feed(frame.data)
            if len(self.capture) == FRAME_BYTES * MAX_FRAMES:
                await self.stop()
            return

        if frame.type == WSMsgType.PING:
            await self.ws.pong(frame.data)
            return
        if frame.type == WSMsgType.PONG:
            return
        if (data := decode(frame)) is None:
            await self.conversation.error("bad_message", retryable=False, turn=self.turn)
            return
        match data["type"]:
            case "listen_start":
                await self.start(data.get("session"))
            case "listen_stop":
                await self.stop()
            case "cancel":
                if self.turn is None or data.get("session") != self.turn.device_number:
                    return
                await self.cancel()
                if not self.retired:
                    await self.conversation.state("idle", self.turn)
            case "wake_start" if self.server.config.wake:
                await self.wake_start(data["seq"])
            case "wake_stop" if self.server.config.wake:
                await self.wake_stop(data["seq"])
            case "ping":
                await self.ws.send_json({"type": "pong", "t": data["t"]})
            case "pong" | "error":
                pass
            case _:
                self.server.log("protocol", code="unknown_type")


class WebSocketServer:
    def __init__(self, config, stt, tts, bridge, canned, log, clock, sleep, pace_clock, wake_stt=None, realtime=None):
        self.config = config
        self.stt = stt
        self.tts = tts
        self.bridge = bridge
        self.canned = canned
        self.log = log
        self.clock = clock
        self.sleep = sleep
        self.pace_clock = pace_clock
        self.wake_stt = wake_stt
        self.realtime = realtime
        self.wake_pattern = compile_pattern(config.wake_pattern)
        self.active = None
        self.connections = set()
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
        if len(self.connections) >= self.config.ws_connection_limit:
            raise web.HTTPServiceUnavailable()
        ws = DeviceSocket(autoping=False, compress=False, max_msg_size=MAX_WS_MESSAGE_BYTES)
        self.connections.add(ws)
        try:
            await ws.prepare(request)
            if await self.authenticate(ws):
                ws.authenticated = True
                await self.serve_device(ws)
            return ws
        finally:
            self.connections.remove(ws)

    async def serve_device(self, ws):
        device = DeviceSession(self, ws)
        try:
            async with self.lock:
                if old := self.active:
                    old.retired = True
                    await old.cancel()
                    await old.ws.close(code=4004)
                self.active = device
                await ws.send_json({"type": "hello_ok", "v": 1, **({"wake": True} if self.config.wake else {})})
            while True:
                try:
                    frame = await ws.receive(timeout=self.config.idle_timeout)
                except TimeoutError:
                    await device.cancel()
                    await ws.close(code=4005)
                    break
                if frame.type in _CLOSED or device.retired:
                    break
                await device.handle(frame)
        finally:
            device.retired = True
            try:
                await device.cancel()
            finally:
                if self.active is device:
                    self.active = None

    async def shutdown(self, app):
        if device := self.active:
            device.retired = True
            await device.cancel()
        await asyncio.gather(*(ws.close() for ws in self.connections if ws.prepared))
        if self.realtime is not None:
            await self.realtime.close()
