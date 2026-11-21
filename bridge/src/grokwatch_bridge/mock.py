import asyncio
import json
import time

import aiohttp

from .contract import BridgeCancelled, BridgeTimeout, BridgeUnavailable, Health, ReplyChunk, Request, wait_until_deadline
from .signing import signature


class MockBridge:
    name = "mock"

    def __init__(self, inbox, *, mode="fixed", text="試験の返事です", delay=0, variant="normal",
                 status="ok", end=False, reply_url="", reply_timeout=90, clock=time.time):
        if mode not in {"fixed", "fail", "silent", "post_reply"}:
            raise ValueError("Invalid mock mode")
        if variant not in {"normal", "tampered", "old_timestamp", "duplicate", "conflict", "cancelled"}:
            raise ValueError("Invalid mock reply variant")
        self.inbox = inbox
        self.mode = mode
        self.text = text
        self.delay = delay
        self.variant = variant
        self.status = status
        self.end = end
        self.reply_url = reply_url
        self.reply_timeout = reply_timeout
        self.clock = clock
        self.last_request = None
        self.post_results = []
        self._active = {}

    async def health(self):
        return Health(True)

    async def cancel(self, session):
        if active := self._active.get(session):
            request, task = active
            self.inbox.cancel(request.request_id)
            if not task.done() and not task.cancelling():
                task.cancel()

    async def send_utterance(self, text, session):
        request = Request.start(session, self.clock, self.reply_timeout)
        self.last_request = request
        self.post_results = []
        answer = asyncio.ensure_future(self.inbox.open(request.request_id, request.reply_token, request.expires_at))
        task = asyncio.create_task(self._respond(request, answer))
        self._active[session] = request, task
        try:
            reply = await wait_until_deadline(task, request, self.clock)
        except asyncio.CancelledError:
            self.inbox.cancel(request.request_id)
            if asyncio.current_task().cancelling():
                raise
            raise BridgeCancelled() from None
        except (BridgeTimeout, BridgeUnavailable):
            self.inbox.cancel(request.request_id)
            raise
        finally:
            self._active.pop(session, None)
            if not task.done() and not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if answer.done() and not answer.cancelled():
                answer.exception()
        yield reply

    async def _respond(self, request, answer):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.mode == "fail":
            raise BridgeUnavailable()
        if self.mode == "fixed":
            self.inbox.cancel(request.request_id)
            return ReplyChunk(self.text, self.status, end_conversation=self.end)
        if self.mode == "post_reply":
            await self._post_reply(request)
        return await asyncio.shield(answer)

    async def _post_reply(self, request):
        if self.variant == "cancelled":
            self.inbox.cancel(request.request_id)
        body = json.dumps(dict(v=1, request_id=request.request_id, status=self.status,
                               text=self.text, end_conversation=self.end),
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(self.clock()) - (121 if self.variant == "old_timestamp" else 0))
        bodies = [body]
        if self.variant in {"duplicate", "conflict"}:
            bodies.append(body if self.variant == "duplicate" else body + b" ")
        try:
            async with aiohttp.ClientSession() as client:
                for raw in bodies:
                    signed = signature(request.reply_token, timestamp, raw)
                    if self.variant == "tampered":
                        raw += b" "
                    headers = {"Content-Type": "application/json", "X-GrokWatch-Request-Id": request.request_id,
                               "X-GrokWatch-Timestamp": timestamp, "X-GrokWatch-Signature": signed}
                    async with client.post(self.reply_url, data=raw, headers=headers,
                                           allow_redirects=False) as response:
                        status = (await response.json())["status"] if response.status == 200 else None
                        self.post_results.append((response.status, status))
        except (aiohttp.ClientError, KeyError, ValueError):
            raise BridgeUnavailable() from None
