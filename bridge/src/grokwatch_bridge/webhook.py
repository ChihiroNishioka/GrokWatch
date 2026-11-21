import asyncio
from collections.abc import Mapping
import json
import time

import aiohttp

from .contract import BridgeCancelled, BridgeUnavailable, Health, Request, wait_for_reply


class Webhook:
    name = "webhook"

    def __init__(self, inbox, url, key, *, reply_timeout=90, timeout=8, clock=time.time):
        self.inbox = inbox
        self.url = url
        self.key = key
        self.reply_timeout = reply_timeout
        self.timeout = timeout
        self.clock = clock
        self._active = {}

    async def health(self):
        return Health(bool(self.url and self.key))

    async def cancel(self, session):
        if active := self._active.get(session):
            request, sending = active
            self.inbox.cancel(request.request_id)
            sending.cancel()

    async def send_utterance(self, text, session):
        if not (await self.health()).available:
            raise BridgeUnavailable()
        request = Request.start(session, self.clock, self.reply_timeout)
        answer = asyncio.ensure_future(self.inbox.open(request.request_id, request.reply_token, request.expires_at))
        sending = asyncio.create_task(self._send(request, text))
        self._active[session] = request, sending
        try:
            try:
                await sending
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                raise BridgeCancelled() from None
            reply = await wait_for_reply(answer, request, self.clock)
        except (BridgeUnavailable, asyncio.CancelledError):
            self.inbox.cancel(request.request_id)
            raise
        finally:
            self._active.pop(session, None)
            if answer.done() and not answer.cancelled():
                answer.exception()
        yield reply

    async def _send(self, request, text):
        headers = {"Authorization": "Bearer " + self.key, "X-Automation-Key": self.key,
                   "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as client:
                async with client.post(self.url, headers=headers, data=encode_body(request.payload(text[:1000])),
                                       allow_redirects=False) as response:
                    if response.status != 200:
                        raise BridgeUnavailable()
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise BridgeUnavailable() from None


def encode_body(payload: Mapping) -> bytes:
    def render():
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    payload = dict(payload)
    body = render()
    while len(body) > 4096:
        payload["text"] = payload["text"][:-1]
        body = render()
    return body
