import asyncio
import base64
import json
from datetime import datetime
import secrets
from uuid import UUID, uuid4

from aiohttp import web
import pytest

from support import eventually, gateway, process_gone, reply_headers, serve


class Inbox:
    def __init__(self):
        self.opened = {}
        self.cancelled = set()

    def open(self, request_id, key, expires):
        future = asyncio.get_running_loop().create_future()
        self.opened[request_id] = (key, expires, future)
        return future

    def cancel(self, request_id):
        from grokwatch_bridge.contract import BridgeCancelled

        self.cancelled.add(request_id)
        future = self.opened[request_id][2]
        if not future.done():
            future.set_exception(BridgeCancelled())


async def collect(adapter, text="質問", session=None):
    from grokwatch_bridge.contract import Session

    session = session or Session("s-20261121-001")
    return [chunk async for chunk in adapter.send_utterance(text, session)]


async def test_factory_and_health_have_no_side_effects(monkeypatch, fake_commands):
    from grokwatch_bridge.contract import Session
    from grokwatch_bridge.factory import create_bridge

    def unexpected(*args, **kwargs):
        pytest.fail("health invoked a subprocess")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", unexpected)
    for name in (None, "webhook", "gbot_cli", "mock"):
        adapter = create_bridge(Inbox(), {} if name is None else {"GROKWATCH_BRIDGE": name})
        assert adapter.name == (name or "webhook")
        health = await adapter.health()
        assert health.available is (name in {"gbot_cli", "mock"})
        assert callable(adapter.send_utterance)
        await adapter.cancel(Session("s-20261121-001"))
    with pytest.raises(ValueError):
        create_bridge(Inbox(), {"GROKWATCH_BRIDGE": "invalid"})
    assert not list(fake_commands.iterdir())


async def test_webhook_request_shape_limits_reply_and_ids():
    from grokwatch_bridge.contract import ReplyChunk, Session
    from grokwatch_bridge.webhook import Webhook

    inbox = Inbox()
    seen = []
    key = secrets.token_urlsafe(32)

    async def handle(request):
        raw = await request.read()
        body = json.loads(raw)
        request_id = body["request_id"]
        token, _, future = inbox.opened[request_id]
        assert request.headers["Authorization"] == "Bearer " + key
        assert request.headers["X-Automation-Key"] == key
        assert request.content_type == "application/json"
        assert set(body) == {"v", "type", "request_id", "session_id", "turn", "text", "lang",
                             "reply_token", "created_at", "expires_at", "max_chars"}
        assert (body["v"], body["type"], body["turn"], body["lang"], body["max_chars"]) == (
            1, "utterance", 1, "ja-JP", 120,
        )
        assert UUID(request_id).version == 4
        assert token == body["reply_token"]
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert len(raw) <= 4096
        if seen:
            # The next Unicode code point must put the serialized body over the limit.
            extended = body | {"text": texts[1][:len(body["text"]) + 1]}
            assert len(json.dumps(extended, ensure_ascii=False, separators=(",", ":")).encode()) > 4096
        future.set_result(ReplyChunk("届いた"))
        seen.append(body)
        return web.Response()

    app = web.Application()
    app.router.add_post("/", handle)
    async with serve(app) as url:
        texts = ["a" * 1001, "𠮷\x01" * 600]
        for i, (text, timeout) in enumerate(zip(texts, [90, 35]), 1):
            adapter = Webhook(inbox, url, key, allow_loopback_http=True, **({} if timeout == 90 else {"reply_timeout": timeout}))
            session = Session(f"s-20261121-{i:03}")
            assert await collect(adapter, text, session) == [ReplyChunk("届いた")]
            sent = seen[-1]
            assert sent["session_id"] == session.session_id
            assert sent["text"] and text.startswith(sent["text"])
            assert len(sent["text"]) <= 1000
            assert (datetime.fromisoformat(sent["expires_at"]) -
                    datetime.fromisoformat(sent["created_at"])).total_seconds() == timeout
        assert len(seen[0]["text"]) == 1000
        assert len(seen[1]["text"]) < 1000
        for field in ("request_id", "reply_token", "session_id"):
            assert seen[0][field] != seen[1][field]


@pytest.mark.parametrize("status", [201, 302, 404, 500, "timeout", "refused"])
async def test_webhook_failures_send_once(status):
    from grokwatch_bridge.contract import BridgeUnavailable
    from grokwatch_bridge.webhook import Webhook

    calls = []
    release = asyncio.Event()

    async def handle(request):
        calls.append(request.path)
        if status == "timeout":
            await release.wait()
            return web.Response()
        return web.Response(status=status, headers={"Location": "/again"})

    app = web.Application()
    app.router.add_post("/{tail:.*}", handle)
    inbox = Inbox()
    async with serve(app) as url:
        assert Webhook(inbox, url, "", allow_loopback_http=True).timeout == 8
        if status != "refused":
            try:
                with pytest.raises(BridgeUnavailable):
                    await collect(Webhook(inbox, url, secrets.token_urlsafe(32), allow_loopback_http=True, timeout=0.05))
            finally:
                release.set()
            assert calls == ["/"]
    if status == "refused":
        with pytest.raises(BridgeUnavailable):
            await collect(Webhook(inbox, url, secrets.token_urlsafe(32), allow_loopback_http=True))
        assert not calls
    assert inbox.cancelled == inbox.opened.keys()


async def test_webhook_cancel():
    from grokwatch_bridge.contract import BridgeCancelled, Session
    from grokwatch_bridge.webhook import Webhook

    async def handle(request):
        return web.Response()

    app = web.Application()
    app.router.add_post("/", handle)
    inbox = Inbox()
    async with serve(app) as url:
        adapter = Webhook(inbox, url, secrets.token_urlsafe(32), allow_loopback_http=True)
        session = Session("s-20261121-001")
        task = asyncio.create_task(collect(adapter, session=session))
        await eventually(lambda: inbox.opened)
        await adapter.cancel(session)
        with pytest.raises(BridgeCancelled):
            await task
    assert inbox.cancelled == inbox.opened.keys()


@pytest.mark.parametrize("mode", ["missing", "ok", "exit", "timeout", "cancel"])
async def test_gbot_invocation_unavailable_and_cancel(mode, monkeypatch, fake_commands, capsys):
    from grokwatch_bridge.contract import BridgeCancelled, BridgeUnavailable, ReplyChunk, Session
    from grokwatch_bridge.factory import create_bridge

    value = secrets.token_urlsafe(32)
    text = '質問\n"引用"'
    env = {"GROKWATCH_BRIDGE": "gbot_cli", "GROKWATCH_GBOT_ARGS": '["--bot","{agent_id}"]',
           "GROKWATCH_AGENT_ID": value}
    adapter = create_bridge(Inbox(), env | (
        {"GROKWATCH_GBOT_BIN": "absent"} if mode == "missing" else {}
    ), gbot_timeout=0.35)
    if mode == "exit":
        monkeypatch.setenv("GW_FIXTURE_GBOT_EXIT", "1")
    elif mode in {"timeout", "cancel"}:
        monkeypatch.setenv("GW_FIXTURE_GBOT_DELAY", "60")
    assert (await adapter.health()).available is (mode != "missing")
    if mode == "ok":
        assert await collect(adapter, text) == [ReplyChunk("試験")]
        assert (fake_commands / "gbot.input").read_text() == text
        assert json.loads((fake_commands / "gbot.json").read_text()) == ["--bot", value]
    elif mode == "cancel":
        session = Session("s-20261121-001")
        task = asyncio.create_task(collect(adapter, session=session))
        await eventually((fake_commands / "gbot.pid").exists)
        await adapter.cancel(session)
        with pytest.raises(BridgeCancelled):
            await task
    else:
        with pytest.raises(BridgeUnavailable) as error:
            await collect(adapter)
        assert value not in str(error.value)
    if mode != "missing":
        process_gone(fake_commands / "gbot.pid")
    captured = capsys.readouterr()
    assert value not in captured.out + captured.err


@pytest.mark.parametrize("mode", ["fixed", "fail", "silent"])
async def test_mock_modes(mode):
    from grokwatch_bridge.contract import BridgeTimeout, BridgeUnavailable, ReplyChunk
    from grokwatch_bridge.mock import MockBridge

    adapter = MockBridge(Inbox(), mode=mode, text="試験返事", delay=0.02, reply_timeout=0.1)
    if mode == "fixed":
        task = asyncio.create_task(collect(adapter))
        await asyncio.sleep(0)
        assert not task.done()
        assert await task == [ReplyChunk("試験返事")]
    else:
        with pytest.raises(BridgeUnavailable if mode == "fail" else BridgeTimeout):
            await collect(adapter)


@pytest.mark.parametrize("variant, statuses", [
    ("normal", [(200, "accepted")]),
    ("tampered", [(401, None)]),
    ("old_timestamp", [(401, None)]),
    ("duplicate", [(200, "accepted"), (200, "duplicate")]),
    ("conflict", [(200, "accepted"), (409, None)]),
    ("cancelled", [(410, None)]),
])
async def test_mock_post_reply_variants(variant, statuses):
    from grokwatch_bridge.contract import BridgeCancelled, BridgeTimeout

    async with gateway(bridge_name="mock", mock_mode="post_reply", mock_variant=variant,
                       reply_timeout=0.25) as (app, _, _, _, _):
        if variant in {"old_timestamp", "tampered", "cancelled"}:
            with pytest.raises(BridgeCancelled if variant == "cancelled" else BridgeTimeout):
                await collect(app.bridge)
        else:
            assert len(await collect(app.bridge)) == 1
        assert app.bridge.post_results == statuses


def test_signing_matches_reference():
    from grokwatch_bridge.signing import signature

    key, request_id, body = secrets.token_urlsafe(32), str(uuid4()), '{"text":"返信"}'.encode()
    assert signature(key, "10000", body) == reply_headers(
        request_id, key, body, 10000,
    )["X-GrokWatch-Signature"]


@pytest.mark.parametrize("scheme", ["http", "file", "ws"])
def test_webhook_rejects_non_https(scheme):
    from grokwatch_bridge.webhook import Webhook

    for allow_loopback in (False, True):
        with pytest.raises(ValueError):
            Webhook(Inbox(), scheme + "://example.invalid/", secrets.token_urlsafe(32),
                    allow_loopback_http=allow_loopback)
