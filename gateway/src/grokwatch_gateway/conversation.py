import asyncio
from dataclasses import dataclass

from grokwatch_bridge.contract import BridgeCancelled, BridgeTimeout, BridgeUnavailable
from grokwatch_bridge.contract import Session

from .audio import SttError, TtsError
from .protocol import FRAME_BYTES, MIN_FRAMES


EMOTIONS = frozenset({"neutral", "happy", "sad", "surprised", "thinking"})


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    device_number: int | None
    bridge_session: Session


class Conversation:
    def __init__(self, ws, *, stt, tts, bridge, canned, log, sleep, clock, pace_clock):
        self.ws = ws
        self.stt = stt
        self.tts = tts
        self.bridge = bridge
        self.canned = canned
        self.log = log
        self.sleep = sleep
        self.clock = clock
        self.pace_clock = pace_clock

    async def state(self, state, turn=None):
        self.log("device_state", state=state)
        message = {"type": "state", "state": state}
        if turn is not None and turn.device_number is not None:
            message["session"] = turn.device_number
        await self.ws.send_json(message)

    async def error(self, code, retryable=True, *, turn=None):
        self.log("conversation_error", code=code)
        message = {"type": "error", "code": code, "retryable": retryable}
        if turn is not None and turn.device_number is not None:
            message["session"] = turn.device_number
        await self.ws.send_json(message)

    async def play(self, pcm, turn, emotion="neutral"):
        await self.state("speaking", turn)
        await self.ws.send_json({
            "type": "tts_start", "sample_rate": 16000,
            "emotion": emotion if isinstance(emotion, str) and emotion in EMOTIONS else "neutral",
        })
        started = self.pace_clock()
        for index, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
            if index >= 10:
                remaining = started + (index - 9) * 0.02 - self.pace_clock()
                if remaining > 0:
                    await self.sleep(remaining)
            await self.ws.send_bytes(pcm[offset:offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\0"))
        await self.ws.send_json({"type": "tts_end"})

    async def fail(self, code, turn):
        if code != "no_speech":
            await self.state("error", turn)
        await self.error(code, turn=turn)
        if pcm := self.canned.get(code):
            await self.play(pcm, turn, "sad")

    async def run(self, pcm, turn):
        try:
            await self._turn(pcm, turn)
        except BridgeCancelled:
            pass
        except (ConnectionError, RuntimeError):
            if self.ws.closed or self.ws.prepared is False:
                return
            await self.fail("internal", turn)
        except Exception:
            await self.fail("internal", turn)
        await self.state("idle", turn)

    async def _turn(self, pcm, turn):
        if len(pcm) < MIN_FRAMES * FRAME_BYTES:
            await self.fail("no_speech", turn)
            return
        started = self.clock()
        try:
            text = (await self.stt(pcm)).strip()
        except SttError:
            await self.fail("stt_failed", turn)
            return
        self.log("transcript", chars=len(text), text=text,
                 latency_ms=max(0, round((self.clock() - started) * 1000)))
        if not text:
            await self.fail("no_speech", turn)
            return

        chunks = []
        status = "ok"
        try:
            async for reply in self.bridge.send_utterance(text, turn.bridge_session):
                chunks.append(reply.text)
                status = reply.status
                if reply.final:
                    break
        except BridgeUnavailable:
            await self.fail("bridge_unavailable", turn)
            return
        except BridgeTimeout:
            await self.fail("bridge_timeout", turn)
            return
        if not chunks:
            await self.fail("bridge_unavailable", turn)
            return
        reply_text = "".join(chunks)
        self.log("speech_reply", chars=len(reply_text), text=reply_text, emotion=reply.emotion)
        if not reply_text.strip():
            await self.fail("reply_error", turn)
            return
        if status == "error":
            await self.state("error", turn)
            await self.error("reply_error", turn=turn)
        try:
            pcm = await self.tts(reply_text)
        except TtsError:
            await self.fail("tts_failed", turn)
            return
        await self.play(pcm, turn, reply.emotion)
