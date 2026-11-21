import asyncio

from grokwatch_bridge.contract import BridgeCancelled, BridgeTimeout, BridgeUnavailable

from .audio import SttError, TtsError
from .protocol import FRAME_BYTES, MIN_FRAMES


class Conversation:
    def __init__(self, ws, *, stt, tts, bridge, canned, log, sleep, clock):
        self.ws = ws
        self.stt = stt
        self.tts = tts
        self.bridge = bridge
        self.canned = canned
        self.log = log
        self.sleep = sleep
        self.clock = clock

    async def state(self, state):
        self.log("device_state", state=state)
        await self.ws.send_json({"type": "state", "state": state})

    async def error(self, code, retryable=True):
        self.log("conversation_error", code=code)
        await self.ws.send_json({"type": "error", "code": code, "retryable": retryable})

    async def play(self, pcm):
        await self.state("speaking")
        await self.ws.send_json({"type": "tts_start", "sample_rate": 16000})
        for index, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
            if index >= 10:
                await self.sleep(0.02)
            await self.ws.send_bytes(pcm[offset:offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\0"))
        await self.ws.send_json({"type": "tts_end"})

    async def fail(self, code):
        if code != "no_speech":
            await self.state("error")
        await self.error(code)
        if pcm := self.canned.get(code):
            await self.play(pcm)

    async def run(self, pcm, session):
        try:
            await self._turn(pcm, session)
        except BridgeCancelled:
            pass
        except (ConnectionError, RuntimeError):
            if self.ws.closed or self.ws.prepared is False:
                return
            await self.fail("internal")
        except Exception:
            await self.fail("internal")
        await self.state("idle")

    async def _turn(self, pcm, session):
        if len(pcm) < MIN_FRAMES * FRAME_BYTES:
            await self.fail("no_speech")
            return
        started = self.clock()
        try:
            text = (await self.stt(pcm)).strip()
        except SttError:
            await self.fail("stt_failed")
            return
        self.log("transcript", chars=len(text), text=text,
                 latency_ms=max(0, round((self.clock() - started) * 1000)))
        if not text:
            await self.fail("no_speech")
            return

        chunks = []
        status = "ok"
        try:
            async for reply in self.bridge.send_utterance(text, session):
                chunks.append(reply.text)
                status = reply.status
                if reply.final:
                    break
        except BridgeUnavailable:
            await self.fail("bridge_unavailable")
            return
        except BridgeTimeout:
            await self.fail("bridge_timeout")
            return
        if not chunks:
            await self.fail("bridge_unavailable")
            return
        reply_text = "".join(chunks)
        self.log("speech_reply", chars=len(reply_text), text=reply_text, emotion=reply.emotion)
        if status == "error":
            if not reply_text:
                await self.fail("reply_error")
                return
            await self.state("error")
            await self.error("reply_error")
        try:
            pcm = await self.tts(reply_text)
        except TtsError:
            await self.fail("tts_failed")
            return
        await self.play(pcm)
