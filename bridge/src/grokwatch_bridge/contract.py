import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import secrets
from typing import Protocol
from uuid import uuid4


class BridgeUnavailable(Exception):
    pass


class BridgeTimeout(Exception):
    pass


class BridgeCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    turn: int = 1


@dataclass(frozen=True, slots=True)
class ReplyChunk:
    text: str
    status: str = "ok"
    emotion: str = "neutral"
    final: bool = True
    end_conversation: bool = False


@dataclass(frozen=True, slots=True)
class Health:
    available: bool


class ReplyInbox(Protocol):
    def open(self, request_id: str, reply_token: str, expires_at: float) -> Awaitable[ReplyChunk]: ...
    def cancel(self, request_id: str) -> None: ...


class Bridge(Protocol):
    name: str

    def send_utterance(self, text: str, session: Session) -> AsyncIterator[ReplyChunk]: ...
    async def health(self) -> Health: ...
    async def cancel(self, session: Session) -> None: ...


@dataclass(frozen=True, slots=True)
class Request:
    session_id: str
    created_at: float
    expires_at: float
    request_id: str = field(default_factory=lambda: str(uuid4()))
    reply_token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @classmethod
    def start(cls, session: Session, clock: Callable[[], float], timeout: float):
        now = clock()
        return cls(session.session_id, now, now + timeout)

    def payload(self, text: str):
        def timestamp(value):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()

        return dict(v=1, type="utterance", request_id=self.request_id, session_id=self.session_id,
                    turn=1, text=text, lang="ja-JP", reply_token=self.reply_token,
                    created_at=timestamp(self.created_at), expires_at=timestamp(self.expires_at),
                    max_chars=120)


async def wait_for_reply(answer, request, clock):
    if (remaining := request.expires_at - clock()) <= 0:
        raise BridgeTimeout()
    try:
        async with asyncio.timeout(remaining):
            return await asyncio.shield(answer)
    except TimeoutError:
        raise BridgeTimeout() from None
