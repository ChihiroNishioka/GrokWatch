import asyncio
from dataclasses import dataclass, field
from typing import Literal

from grokwatch_bridge.contract import BridgeCancelled, BridgeTimeout, ReplyChunk


State = Literal["pending", "answered", "expired", "cancelled"]


@dataclass(slots=True)
class Entry:
    token: str = field(repr=False)
    expires_at: float
    future: asyncio.Future = field(repr=False)
    state: State = "pending"
    terminal_at: float | None = None
    digest: bytes | None = None


class Registry:
    def __init__(self, clock, retention=600):
        self.clock = clock
        self.retention = retention
        self._entries = {}

    def open(self, request_id, reply_token, expires_at):
        self.sweep()
        if request_id in self._entries:
            raise ValueError("Request already registered")
        future = asyncio.get_running_loop().create_future()
        future.add_done_callback(self._consume_exception)
        self._entries[request_id] = Entry(reply_token, expires_at, future)
        return future

    @staticmethod
    def _consume_exception(future):
        if not future.cancelled():
            future.exception()

    def sweep(self):
        now = self.clock()
        for request_id, entry in list(self._entries.items()):
            if now >= entry.expires_at:
                if entry.state == "pending":
                    self._finish(entry, "expired", BridgeTimeout(), at=entry.expires_at)
                entry.token = ""
            if entry.terminal_at is not None and now >= entry.terminal_at + self.retention:
                del self._entries[request_id]

    def get(self, request_id):
        self.sweep()
        return self._entries.get(request_id)

    def state(self, request_id):
        entry = self.get(request_id)
        return entry.state if entry else None

    def tokens(self):
        return (entry.token for entry in self._entries.values() if entry.token)

    def cancel(self, request_id):
        if (entry := self.get(request_id)) and entry.state == "pending":
            self._finish(entry, "cancelled", BridgeCancelled())
            entry.token = ""

    def accept(self, entry, digest, reply: ReplyChunk):
        entry.digest = digest
        self._finish(entry, "answered", reply)

    def _finish(self, entry, state: State, result, *, at=None):
        entry.state = state
        entry.terminal_at = self.clock() if at is None else at
        if not entry.future.done():
            if isinstance(result, Exception):
                entry.future.set_exception(result)
            else:
                entry.future.set_result(result)
