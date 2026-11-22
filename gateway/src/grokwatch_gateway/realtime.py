import asyncio
import base64
import binascii
from contextlib import suppress
from datetime import datetime
import json

import aiohttp
from grokwatch_bridge.contract import Health

from .protocol import FRAME_BYTES, MIN_FRAMES
from .resample import Resampler
from .tools import JST, TOOL_DEFINITIONS, Tools


OPEN_TIMEOUT = 5
MAX_TOOL_ROUNDS = 4
WEEKDAYS = "月火水木金土日"

INSTRUCTIONS = """あなたは腕時計型の端末に入っている音声アシスタント「Grok Bot」です。オーナーと日本語で話します。

話し方:
- 声で聞く前提で、1〜3文の短い話し言葉で答える。
- Markdown、記号、URL、絵文字は使わない。数字や時刻は読み上げやすい言い方にする。
- 分からないことを作り話で答えない。

現在の日時（日本時間）: {now}

道具:
- オーナーの予定（スケジュール）を聞かれたら get_schedule を使う。
- オーナーのメールを聞かれたら get_mail を使う。本文は読めないので、差出人と件名だけ伝える。
- ニュースや天気など、最新の情報が必要なときは web_search を使う。
- 調べもの、整理、下書きなどの作業を頼まれたら delegate_to_grok_bot で Grok Bot に頼み、「やっておくね」のように短く伝える。
- 道具が「timeout」や「unavailable」などの error を返したら、「いま確認できなかった」と伝える。
- delegate_to_grok_bot が failed を返したら「頼めなかったから、あとでチャットで送ってね」と伝える。not_configured を返したら「作業の依頼はまだ使えないよ」と伝える。

禁止:
- メールやメッセージの送信、削除、購入、支払い、予約の確定は、決して delegate_to_grok_bot に渡さない。頼まれたら「それはチャットで頼んでね」とだけ答える。
"""


class RealtimeError(Exception):
    pass


class UnavailableBridge:
    """Fallback bridge when no webhook is configured: every utterance ends in canned audio."""

    name = "none"

    async def health(self):
        return Health(False)

    async def cancel(self, session):
        pass

    async def send_utterance(self, text, session):
        from grokwatch_bridge.contract import BridgeUnavailable
        raise BridgeUnavailable()
        yield


class _Turn:
    def __init__(self):
        self.up = Resampler(16000, 24000)
        self.backlog = []
        self.ready = False
        self.failed = False
        self.pump = None


class RealtimeSession:
    """One OpenAI Realtime connection, reused between turns and closed after an idle period."""

    def __init__(self, config, log, clock, tools=None, *, open_timeout=OPEN_TIMEOUT):
        self.config = config
        self.log = log
        self.clock = clock
        self.tools = tools or Tools(config, log, clock)
        self.open_timeout = open_timeout
        self.http = None
        self.ws = None
        self.reader = None
        self.opening = None
        self.idle = None
        self.closing = None
        self.current = None
        self.collect = False
        self.events = asyncio.Queue()
        self.background = set()

    # -- connection -------------------------------------------------------------------------

    def alive(self):
        return self.ws is not None and not self.ws.closed

    def instructions(self):
        now = datetime.fromtimestamp(self.clock(), JST)
        text = f"{now:%Y年%m月%d日}（{WEEKDAYS[now.weekday()]}曜日） {now:%H:%M}"
        return INSTRUCTIONS.format(now=text)

    def session_config(self):
        return {
            "type": "realtime", "model": self.config.realtime_model, "instructions": self.instructions(),
            "output_modalities": ["audio"],
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": 24000}, "turn_detection": None},
                "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": self.config.realtime_voice},
            },
            "tools": TOOL_DEFINITIONS, "tool_choice": "auto",
        }

    async def send(self, event):
        ws = self.ws
        if ws is None or ws.closed:
            raise RealtimeError()
        try:
            await ws.send_str(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        except (aiohttp.ClientError, ConnectionError, RuntimeError, OSError):
            raise RealtimeError() from None

    async def connect(self):
        started = self.clock()
        http = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(self.open_timeout):
                ws = await http.ws_connect(
                    self.config.realtime_url, params={"model": self.config.realtime_model},
                    headers={"Authorization": "Bearer " + self.config.openai_api_key},
                    heartbeat=20, autoping=True, compress=0, max_msg_size=0,
                )
            self.http, self.ws = http, ws
            self.reader = asyncio.create_task(self.read(ws))
            await self.send({"type": "session.update", "session": self.session_config()})
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError, RealtimeError):
            await self.close_connection()
            with suppress(Exception):
                await http.close()
            self.log("realtime_open", level="warning", code="failed")
            raise RealtimeError() from None
        except BaseException:
            await asyncio.shield(http.close())
            raise
        self.log("realtime_open", latency_ms=max(0, round((self.clock() - started) * 1000)))

    async def read(self, ws):
        try:
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        event = json.loads(message.data)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and self.collect:
                        self.events.put_nowait(event)
                elif message.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    break
        except (aiohttp.ClientError, ConnectionError, RuntimeError, OSError):
            pass
        finally:
            if self.ws is ws:
                self.ws = None
            self.events.put_nowait(None)

    async def close_connection(self):
        ws, self.ws = self.ws, None
        reader, self.reader = self.reader, None
        http, self.http = self.http, None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if ws is not None:
            with suppress(Exception):
                await ws.close()
        if http is not None:
            with suppress(Exception):
                await http.close()

    def drop(self):
        """Close the connection in a task that survives the cancellation of the caller."""
        if self.closing is None or self.closing.done():
            self.closing = asyncio.create_task(self.close_connection())
        return self.closing

    async def close(self):
        self.cancel_idle()
        for task in list(self.background):
            task.cancel()
        if self.current is not None and self.current.pump is not None:
            self.current.pump.cancel()
            await asyncio.gather(self.current.pump, return_exceptions=True)
        self.current = None
        await asyncio.shield(self.drop())
        if self.opening is not None:
            self.opening.cancel()
            await asyncio.gather(self.opening, return_exceptions=True)
            await asyncio.shield(self.drop())
        await asyncio.gather(*self.background, return_exceptions=True)

    def arm_idle(self):
        self.cancel_idle()
        self.idle = asyncio.create_task(self.expire())

    def cancel_idle(self):
        if self.idle is not None and self.idle is not asyncio.current_task():
            self.idle.cancel()
        self.idle = None

    async def expire(self):
        await asyncio.sleep(self.config.realtime_idle)
        if self.current is None and self.ws is not None:
            self.log("realtime_closed", code="idle")
            await asyncio.shield(self.drop())

    # -- turns (called by the device session) -------------------------------------------------

    def background_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return task

    async def begin(self):
        """Called on listen_start: open the session if needed and warm the context cache."""
        self.cancel_idle()
        if self.current is not None and self.current.pump is not None:
            self.current.pump.cancel()
        turn = self.current = _Turn()
        if not self.alive() and (self.opening is None or self.opening.done()):
            self.opening = asyncio.create_task(self.connect())
            self.opening.add_done_callback(lambda task: task.cancelled() or task.exception())
        turn.pump = asyncio.create_task(self.pump(turn))
        self.background_task(self.tools.refresh())

    async def pump(self, turn):
        reuse = self.alive() and (self.opening is None or self.opening.done())
        try:
            if self.opening is not None and not self.opening.done():
                await asyncio.shield(self.opening)
            elif not self.alive():
                self.opening = asyncio.create_task(self.connect())
                self.opening.add_done_callback(lambda task: task.cancelled() or task.exception())
                await asyncio.shield(self.opening)
            if not self.alive():
                raise RealtimeError()
            if reuse:
                await self.send({"type": "session.update", "session": {
                    "type": "realtime", "instructions": self.instructions()}})
            await self.send({"type": "input_audio_buffer.clear"})
            while turn.backlog:
                await self.send({"type": "input_audio_buffer.append", "audio": turn.backlog.pop(0)})
            turn.ready = True
        except (RealtimeError, aiohttp.ClientError, OSError):
            turn.failed = True
        except asyncio.CancelledError:
            turn.failed = True
            raise

    async def feed(self, frame):
        turn = self.current
        if turn is None or turn.failed:
            return
        audio = base64.b64encode(turn.up.process(frame)).decode("ascii")
        if not turn.ready:
            turn.backlog.append(audio)
            return
        try:
            await self.send({"type": "input_audio_buffer.append", "audio": audio})
        except RealtimeError:
            turn.failed = True

    async def discard(self):
        """Called when listening is cancelled or restarted: forget the audio sent so far."""
        turn, self.current = self.current, None
        if turn is None:
            return
        if turn.pump is not None:
            turn.pump.cancel()
            await asyncio.gather(turn.pump, return_exceptions=True)
        if turn.ready and self.alive():
            with suppress(RealtimeError):
                await self.send({"type": "input_audio_buffer.clear"})
        self.arm_idle()

    async def run(self, conversation, pcm, turn):
        """Drop-in for Conversation.run: answers the buffered utterance through Realtime."""
        rt, self.current = self.current, None
        fallback = False
        try:
            fallback = await self.respond(conversation, pcm, turn, rt)
        except asyncio.CancelledError:
            self.collect = False
            await asyncio.shield(self.drop())
            raise
        except (ConnectionError, RuntimeError):
            if conversation.ws.closed or conversation.ws.prepared is False:
                return
            fallback = True
        except Exception:
            fallback = True
        finally:
            self.collect = False
            self.arm_idle()
        if fallback:
            await self.fall_back(conversation, pcm, turn)
        else:
            await conversation.state("idle", turn)

    async def fall_back(self, conversation, pcm, turn):
        if len(pcm) >= MIN_FRAMES * FRAME_BYTES and not (await conversation.bridge.health()).available:
            await conversation.fail("bridge_unavailable", turn)
            await conversation.state("idle", turn)
            return
        await conversation.run(pcm, turn)

    async def respond(self, conversation, pcm, turn, rt):
        """Returns True when the turn must be handled by the fallback pipeline."""
        if rt is None or len(pcm) < MIN_FRAMES * FRAME_BYTES:
            if rt is not None and rt.pump is not None:
                rt.pump.cancel()
                await asyncio.gather(rt.pump, return_exceptions=True)
                if rt.ready and self.alive():
                    with suppress(RealtimeError):
                        await self.send({"type": "input_audio_buffer.clear"})
            return True
        started = self.clock()
        try:
            await rt.pump
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            rt.failed = True
        if rt.failed or not rt.ready or not self.alive():
            self.log("realtime_fallback", level="warning", code="connect")
            await asyncio.shield(self.drop())
            return True
        while not self.events.empty():
            self.events.get_nowait()
        self.collect = True
        try:
            await self.send({"type": "input_audio_buffer.commit"})
            await self.send({"type": "response.create"})
        except RealtimeError:
            self.log("realtime_fallback", level="warning", code="send")
            await asyncio.shield(self.drop())
            return True

        stream = None
        rounds = 0
        frames = 0
        up = Resampler(24000, 16000)

        async def end(code):
            nonlocal stream
            if stream is not None:
                await stream.finish()
                self.log("realtime_turn", code=code, frames=stream.index,
                         latency_ms=max(0, round((self.clock() - started) * 1000)))
            await asyncio.shield(self.drop()) if code != "ok" else None

        while True:
            try:
                async with asyncio.timeout(self.config.realtime_response_timeout):
                    event = await self.events.get()
            except TimeoutError:
                event = None
                reason = "timeout"
            else:
                reason = "closed"
            if event is None:
                if stream is None:
                    self.log("realtime_fallback", level="warning", code=reason)
                    await asyncio.shield(self.drop())
                    return True
                self.log("realtime_dropped", level="warning", code=reason)
                await end("dropped")
                return False
            kind = event.get("type")
            if kind == "response.output_audio.delta":
                try:
                    audio = base64.b64decode(event.get("delta") or "", validate=True)
                except (binascii.Error, ValueError, TypeError):
                    continue
                if stream is None:
                    stream = await conversation.open_stream(turn, "neutral")
                    self.log("realtime_first_audio",
                             latency_ms=max(0, round((self.clock() - started) * 1000)))
                await stream.write(up.process(audio))
            elif kind == "error":
                err = event.get("error")
                code = err.get("code") if isinstance(err, dict) and isinstance(err.get("code"), str) else "error"
                self.log("realtime_error", level="warning", code=code)
                if stream is None:
                    await asyncio.shield(self.drop())
                    return True
                await end("error")
                return False
            elif kind == "response.done":
                response = event.get("response")
                response = response if isinstance(response, dict) else {}
                calls = [item for item in response.get("output") or []
                         if isinstance(item, dict) and item.get("type") == "function_call"]
                if calls and rounds < MAX_TOOL_ROUNDS:
                    rounds += 1
                    if not await self.run_tools(calls):
                        if stream is None:
                            await asyncio.shield(self.drop())
                            return True
                        await end("error")
                        return False
                    continue
                if stream is None:
                    self.log("realtime_fallback", level="warning", code="no_audio")
                    await asyncio.shield(self.drop())
                    return True
                await end("ok")
                return False

    async def run_tools(self, calls):
        outputs = await asyncio.gather(*(
            self.tools.call(call.get("name"), call.get("arguments")) for call in calls))
        try:
            for call, output in zip(calls, outputs):
                call_id = call.get("call_id")
                if not isinstance(call_id, str):
                    continue
                await self.send({"type": "conversation.item.create", "item": {
                    "type": "function_call_output", "call_id": call_id, "output": output}})
            await self.send({"type": "response.create"})
        except RealtimeError:
            return False
        return True
