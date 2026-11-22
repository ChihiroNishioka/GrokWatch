import asyncio
import gzip
import hmac
import secrets
from uuid import uuid4

import pytest

from support import gateway, post, reply_body, reply_headers


@pytest.fixture
async def inbox():
    now = [10_000]
    async with gateway(clock=lambda: now[0], retention=10) as (app, _, client, _, base):
        key = secrets.token_urlsafe(32)

        def register():
            request_id = str(uuid4())
            return request_id, app.registry.open(request_id, key, now[0] + 90)

        yield now, app.registry, client, base, key, register


async def test_valid_duplicate_and_conflicting_reply(inbox):
    now, registry, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(request_id)
    assert await post(client, base, request_id, key, body, now[0]) == (200, {"status": "accepted"})
    assert registry.state(request_id) == "answered"
    assert (await answer).text == "返事"
    assert await post(client, base, request_id, key, body, now[0]) == (200, {"status": "duplicate"})
    assert (await post(client, base, request_id, key, body + b" ", now[0]))[0] == 409


async def test_get_reply_path_returns_method_not_allowed(inbox):
    _, _, client, base, _, _ = inbox
    async with client.get(base + "/v1/reply") as response:
        assert response.status == 405


@pytest.mark.parametrize("offset, expected", [(-121, 401), (121, 401), (-120, 200), (120, 200)])
async def test_timestamp_window(inbox, offset, expected):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    assert (await post(client, base, request_id, key, timestamp=now[0] + offset))[0] == expected


async def test_expired_cancelled_unknown_and_purged(inbox):
    now, registry, client, base, key, register = inbox
    pending, _ = register()
    answered, _ = register()
    cancelled, _ = register()
    assert (await post(client, base, answered, key, timestamp=now[0]))[0] == 200
    registry.cancel(cancelled)
    wrong = secrets.token_urlsafe(32)
    assert (await post(client, base, cancelled, wrong, timestamp=now[0]))[0] == 410
    assert (await post(client, base, str(uuid4()), wrong, timestamp=now[0]))[0] == 404
    now[0] += 90
    assert (await post(client, base, pending, wrong, timestamp=now[0]))[0] == 410
    assert registry.state(pending) == "expired"
    # An answered ID retained across its deadline rejects even the accepted bytes.
    recently_answered, _ = register()
    now[0] += 89
    assert (await post(client, base, recently_answered, key, timestamp=now[0]))[0] == 200
    now[0] += 1
    assert (await post(client, base, recently_answered, key, timestamp=now[0]))[0] == 410
    assert (await post(client, base, answered, key, timestamp=now[0]))[0] == 404


async def test_signature_required_even_after_accept(inbox, monkeypatch):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    body = reply_body(request_id)
    calls = []
    original = hmac.compare_digest

    def capture(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(hmac, "compare_digest", capture)
    headers = reply_headers(request_id, key, body, now[0])
    signature = headers["X-GrokWatch-Signature"]
    for data, signed, expected in [
        (body + b" ", signature, 401), (body, signature, 200),
        (body, None, 422), (body, signature[7:], 422),
        (body, signature[:-1] + ("0" if signature[-1] != "0" else "1"), 401),
    ]:
        actual = headers.copy()
        if signed is None:
            del actual["X-GrokWatch-Signature"]
        else:
            actual["X-GrokWatch-Signature"] = signed
        async with client.post(base + "/v1/reply", data=data, headers=actual) as response:
            assert response.status == expected
    assert calls
    assert (await post(client, base, request_id, secrets.token_urlsafe(32), timestamp=now[0]))[0] == 401


async def test_body_limit(inbox):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    body = reply_body(request_id).ljust(8192)
    async with client.post(base + "/v1/reply", data=body + b" ") as response:
        assert response.status == 413
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 200


async def test_content_encoding_is_rejected_without_decompressing_the_received_body(inbox, monkeypatch):
    now, registry, client, base, key, register = inbox
    request_id, answer = register()
    body = b"x" * 10000
    compressed = gzip.compress(body)
    assert len(compressed) < 8192 < len(body)
    headers = reply_headers(request_id, key, compressed, now[0])
    headers["Content-Encoding"] = "gzip"
    import aiohttp.compression_utils
    backend = aiohttp.compression_utils.ZLibBackend._zlib_backend
    original = backend.decompressobj
    decompressions = []

    def track_decompression(*args, **kwargs):
        decompressions.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "decompressobj", track_decompression)
    async with client.post(base + "/v1/reply", data=compressed, headers=headers) as response:
        assert response.status == 415
    assert decompressions == []
    assert registry.state(request_id) == "pending"
    valid = reply_body(request_id)
    assert await post(client, base, request_id, key, valid, now[0]) == (200, {"status": "accepted"})
    assert (await answer).text == "返事"


@pytest.mark.parametrize("fields", [
    {"v": True}, {"v": 2}, {"v": None}, {"status": "other"}, {"status": []},
    {"text": 1}, {"text": "あ" * 401}, {"emotion": False}, {"end_conversation": 1},
    {"request_id": "wrong"},
])
async def test_malformed_fields(inbox, fields):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    # Make a separate dictionary so request_id can itself be replaced.
    import json
    body = json.dumps(json.loads(reply_body(request_id)) | fields).encode()
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 422


async def test_signed_reply_is_cleaned_before_tts(inbox):
    now, _, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(
        request_id,
        text="**晴れ** [資料](https://example.test) 次はhttps://example.test/docs。続きです。 😊",
    )
    assert await post(client, base, request_id, key, body, now[0]) == (
        200, {"status": "accepted"},
    )
    assert (await answer).text == "晴れ 資料リンク 次はリンク。続きです。"


async def test_reply_that_cleans_to_empty_is_rejected_without_completing_request(inbox):
    now, registry, client, base, key, register = inbox
    request_id, answer = register()
    empty_after_cleanup = reply_body(request_id, text="**_~#😊")
    assert (await post(client, base, request_id, key, empty_after_cleanup, now[0]))[0] == 422
    assert registry.state(request_id) == "pending"
    corrected = reply_body(request_id, text="返事です")
    assert await post(client, base, request_id, key, corrected, now[0]) == (
        200, {"status": "accepted"},
    )
    assert (await answer).text == "返事です"


async def test_keycap_emoji_only_reply_is_rejected(inbox):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    body = reply_body(request_id, text="1️⃣")
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 422


async def test_markdown_horizontal_rule_only_reply_is_rejected(inbox):
    now, _, client, base, key, register = inbox
    request_id, _ = register()
    body = reply_body(request_id, text="---")
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 422


async def test_emoji_presentation_sequences_are_rejected_as_a_unit(inbox):
    now, _, client, base, key, register = inbox
    for text in ("㊗️", "↔️", "‼️"):
        request_id, _ = register()
        body = reply_body(request_id, text=text)
        assert (await post(client, base, request_id, key, body, now[0]))[0] == 422


async def test_speech_cleanup_preserves_japanese_units(inbox):
    now, _, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(request_id, text="時速60㎞です。")
    assert await post(client, base, request_id, key, body, now[0]) == (
        200, {"status": "accepted"},
    )
    assert (await answer).text == "時速60㎞です。"


async def test_markdown_url_does_not_swallow_following_japanese_text(inbox):
    now, _, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(request_id, text="[資料](https://example.invalid)です。")
    assert await post(client, base, request_id, key, body, now[0]) == (
        200, {"status": "accepted"},
    )
    assert (await answer).text == "資料リンクです。"


async def test_malformed_headers_and_json(inbox):
    now, _, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(request_id, text="あ" * 400)
    headers = reply_headers(request_id, key, body, now[0])
    for name in headers:
        for value in (None, "invalid"):
            attempted = headers.copy()
            if value is None:
                del attempted[name]
            else:
                attempted[name] = value
            async with client.post(base + "/v1/reply", data=body, headers=attempted) as response:
                assert response.status == 422
    for malformed in (b"[]", b"{}", b"{", b"\xff"):
        assert (await post(client, base, request_id, key, malformed, now[0]))[0] == 422
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 200
    assert (await answer).emotion == "neutral"


async def test_unknown_emotion(inbox):
    now, _, client, base, key, register = inbox
    request_id, answer = register()
    body = reply_body(request_id, emotion="other")
    assert (await post(client, base, request_id, key, body, now[0]))[0] == 200
    assert (await answer).emotion == "neutral"


@pytest.mark.parametrize("same", [True, False])
async def test_simultaneous_terminal_transition(inbox, same):
    now, registry, client, base, key, register = inbox
    request_id, answer = register()
    first = reply_body(request_id)
    second = first if same else reply_body(request_id, text="違う返事")
    responses = await asyncio.gather(
        post(client, base, request_id, key, first, now[0]),
        post(client, base, request_id, key, second, now[0]),
    )
    assert responses.count((200, {"status": "accepted"})) == 1
    assert ((200, {"status": "duplicate"}) if same else (409, None)) in responses
    assert (await answer).text in {"返事", "違う返事"}
    registry.cancel(request_id)
    assert registry.state(request_id) == "answered"


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_reply_and_cancel_follow_first_terminal_transition(inbox, cancel_first):
    from grokwatch_bridge.contract import BridgeCancelled

    now, registry, client, base, key, register = inbox
    request_id, answer = register()
    if cancel_first:
        registry.cancel(request_id)
        assert (await post(client, base, request_id, key, timestamp=now[0]))[0] == 410
        with pytest.raises(BridgeCancelled):
            await answer
        assert registry.state(request_id) == "cancelled"
    else:
        assert await post(client, base, request_id, key, timestamp=now[0]) == (
            200, {"status": "accepted"},
        )
        registry.cancel(request_id)
        assert await post(client, base, request_id, key, timestamp=now[0]) == (
            200, {"status": "duplicate"},
        )
        assert (await answer).text == "返事"
        assert registry.state(request_id) == "answered"


@pytest.mark.parametrize("missing", ["url", "key", None])
async def test_healthz_shape_and_no_secrets(missing):
    from grokwatch_bridge.webhook import Webhook

    key = secrets.token_urlsafe(32)
    url = "http://127.0.0.1:1/" + secrets.token_urlsafe(8)
    adapter = Webhook(None, "" if missing == "url" else url, "" if missing == "key" else key,
                      allow_loopback_http=True)
    async with gateway(bridge=adapter) as (_, config, client, _, base):
        async with client.get(base + "/healthz") as response:
            assert response.status == 200
            assert await response.json() == {
                "status": "ok" if missing is None else "degraded",
                "bridge": {"name": "webhook", "available": missing is None},
                "stt": "mock", "tts": "mock", "device_connected": False, "wake": False, "version": "1.2.1",
            }
            response_body = await response.text()
            assert all(value not in response_body for value in (key, url, config.device_token))


def test_reply_listen_default_loopback():
    from grokwatch_gateway.config import Config

    def load(**values):
        return Config.from_env({"GROKWATCH_ALLOW_ENV_SECRETS": "1",
                                "GROKWATCH_DEVICE_TOKEN": secrets.token_urlsafe(32), **values})

    assert (load().reply_host, load().reply_port) == ("127.0.0.1", 8767)
    assert load(GROKWATCH_REPLY_LISTEN="127.0.0.1:9876").reply_port == 9876
    with pytest.raises(ValueError):
        load(GROKWATCH_REPLY_LISTEN="*:8767")
