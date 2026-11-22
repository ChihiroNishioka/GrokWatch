import asyncio

import pytest

from support import connected, eventually, gateway


@pytest.mark.parametrize("text", [
    "Hi Grok", "ハイ、グロック", "はいぐろっく", "ヘイ グロック！", "hey grok", "OK Grok", "ねえグロック",
    "HEY, GROK.", "ハーイ グロク", "ｈｉ ｇｒｏｋ", "ハイ・グロッグ", "えー、はい、ぐろっく", "okグロック",
    "ネーグロック", "オーケー グロック", "hi groq", "Hi Grock",
])
def test_wake_phrases(text):
    from grokwatch_gateway.wake import is_wake

    assert is_wake(text)


@pytest.mark.parametrize("text", ["はい", "グロック", "ハイキング", "", "こんにちは", "grok", "hi", "ハイ 天気"])
def test_non_wake_phrases(text):
    from grokwatch_gateway.wake import is_wake

    assert not is_wake(text)


def test_normalize():
    from grokwatch_gateway.wake import normalize

    assert normalize(" Ｈｉ、 はい ぐろっく！ ") == "hiハイグロック"
    assert normalize("ハーイ") == "ハーイ"


def test_custom_pattern():
    from grokwatch_gateway.config import Config
    from grokwatch_gateway.wake import is_wake

    assert is_wake("ねえ ポチ", "ネエポチ")
    assert not is_wake("Hi Grok", "ネエポチ")
    with pytest.raises(ValueError, match="WAKE_PATTERN"):
        Config(device_token="a" * 32, wake_pattern="(")
    with pytest.raises(ValueError, match="WAKE_PATTERN"):
        Config.from_env({"GROKWATCH_DEVICE_TOKEN": "a" * 32, "GROKWATCH_ALLOW_ENV_SECRETS": "1",
                         "GROKWATCH_WAKE_PATTERN": "["})


def test_config_env():
    from grokwatch_gateway.config import Config

    env = {"GROKWATCH_ALLOW_ENV_SECRETS": "1", "GROKWATCH_DEVICE_TOKEN": "a" * 32}
    assert not Config.from_env(env).wake
    config = Config.from_env(env | {"GROKWATCH_WAKE": "1", "GROKWATCH_WAKE_MODEL": "m.bin"})
    assert config.wake and config.wake_model == "m.bin"


@pytest.mark.parametrize("message", [
    {"type": "wake_start"}, {"type": "wake_start", "seq": 0}, {"type": "wake_start", "seq": -1},
    {"type": "wake_start", "seq": True}, {"type": "wake_stop", "seq": 2**63}, {"type": "wake_stop", "seq": "1"},
    {"type": "wake_stop", "seq": 1.5}, {"type": "wake_stop"},
])
def test_protocol_rejects_bad_seq(message):
    import json
    from types import SimpleNamespace

    from aiohttp import WSMsgType
    from grokwatch_gateway.protocol import decode

    assert decode(SimpleNamespace(type=WSMsgType.TEXT, data=json.dumps(message))) is None


@pytest.mark.parametrize("kind", ["wake_start", "wake_stop"])
def test_protocol_accepts_seq(kind):
    import json
    from types import SimpleNamespace

    from aiohttp import WSMsgType
    from grokwatch_gateway.protocol import decode

    for seq in (1, 2**63 - 1):
        assert decode(SimpleNamespace(type=WSMsgType.TEXT, data=json.dumps({"type": kind, "seq": seq})))["seq"] == seq


class GatedStt:
    def __init__(self, text="Hi Grok", fail=False):
        self.text, self.fail = text, fail
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = 0
        self.gated = False

    async def __call__(self, pcm):
        from grokwatch_gateway.audio import SttError

        self.calls.append(len(pcm))
        self.started.set()
        if self.gated:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
        if self.fail:
            raise SttError()
        return self.text


async def quiet(device, timeout=0.2):
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(timeout):
            await device.receive()


async def test_hello_ok_wake_flag():
    async with gateway(wake=True) as (_, config, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            from support import Device

            device = Device(ws)
            await device.hello(config.device_token)
            assert await device.receive() == {"type": "hello_ok", "v": 1, "wake": True}
    async with gateway() as (_, config, client, base, _):
        async with client.ws_connect(base + "/v1/ws") as ws:
            from support import Device

            device = Device(ws)
            await device.hello(config.device_token)
            assert await device.receive() == {"type": "hello_ok", "v": 1}


@pytest.fixture
def wake_gateway():
    def make(stt, **settings):
        return gateway(wake=True, wake_stt=stt, **settings)
    return make


async def test_wake_hit_and_miss(wake_gateway, capsys):
    stt = GatedStt()
    async with wake_gateway(stt, log_text=True) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1, frames=20)
            assert await device.receive() == {"type": "wake", "seq": 1, "hit": True}
            assert stt.calls == [20 * 640]
            stt.text = "こんにちは"
            await device.wake(2)
            assert await device.receive() == {"type": "wake", "seq": 2, "hit": False}
    out = capsys.readouterr().out
    assert '"event":"wake_check"' in out and '"hit":true' in out and '"frames":20' in out


async def test_wake_log_hides_text_by_default(wake_gateway, capsys):
    async with wake_gateway(GatedStt("Hi Grok")) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            await device.receive()
    out = capsys.readouterr().out
    assert '"event":"wake_check"' in out and "Hi Grok" not in out


async def test_wake_short_segment_skips_stt(wake_gateway):
    stt = GatedStt()
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1, frames=14)
            assert await device.receive() == {"type": "wake", "seq": 1, "hit": False}
            assert stt.calls == []


async def test_wake_stt_failure_is_miss(wake_gateway):
    async with wake_gateway(GatedStt(fail=True)) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            assert await device.receive() == {"type": "wake", "seq": 1, "hit": False}


async def test_wake_stop_with_other_seq_ignored(wake_gateway):
    stt = GatedStt()
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1, stop=False)
            await device.send("wake_stop", seq=2)
            await quiet(device)
            assert stt.calls == []
            await device.send("wake_stop", seq=1)
            assert await device.receive() == {"type": "wake", "seq": 1, "hit": True}


async def test_wake_frame_cap(wake_gateway):
    stt = GatedStt()
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1, frames=140)
            assert (await device.receive())["hit"] is True
            assert stt.calls == [125 * 640]


async def test_wake_busy_conversation_is_miss(wake_gateway):
    stt = GatedStt()
    release = asyncio.Event()

    async def convo_stt(pcm):
        await release.wait()
        return "質問"

    async with gateway(wake=True, wake_stt=stt, stt=convo_stt, bridge_name="mock") as (
        _, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop()
            await device.wake(1)
            assert await device.receive() == {"type": "wake", "seq": 1, "hit": False}
            assert stt.calls == []
            release.set()
            await device.idle()


async def test_new_wake_start_cancels_pending_check(wake_gateway):
    stt = GatedStt()
    stt.gated = True
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            await stt.started.wait()
            stt.gated = False
            await device.wake(2)
            assert await device.receive() == {"type": "wake", "seq": 2, "hit": True}
            assert stt.cancelled == 1
            await quiet(device)


async def test_listen_start_discards_wake(wake_gateway):
    stt = GatedStt()
    stt.gated = True
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            await stt.started.wait()
            await device.start()
            assert stt.cancelled == 1
            await device.wake(2, frames=5, stop=False)
            await device.send("listen_start", session=7)
            assert await device.receive() == {"type": "state", "state": "listening", "session": 7}
            await device.send("wake_stop", seq=2)
            await quiet(device)


async def test_wake_frames_during_listening_go_to_utterance(wake_gateway):
    stt = GatedStt()
    async with wake_gateway(stt, bridge_name="mock") as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1, frames=5, stop=False)
            await device.start()
            await device.stop(frames=15)
            await device.idle()
            assert stt.calls == []


async def test_disconnect_cancels_wake_check(wake_gateway):
    stt = GatedStt()
    stt.gated = True
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            await stt.started.wait()
        await eventually(lambda: stt.cancelled == 1)


async def test_replacement_cancels_wake_check(wake_gateway):
    stt = GatedStt()
    stt.gated = True
    async with wake_gateway(stt) as (_, config, client, base, _):
        async with connected(client, base, config) as first:
            await first.wake(1)
            await stt.started.wait()
            async with connected(client, base, config):
                await eventually(lambda: stt.cancelled == 1)


async def test_disabled_gateway_ignores_wake(capsys):
    stt = GatedStt()
    async with gateway(wake_stt=stt) as (_, config, client, base, _):
        async with connected(client, base, config) as device:
            await device.wake(1)
            await quiet(device)
            assert stt.calls == []
            await device.send("ping", t=3)
            assert await device.receive() == {"type": "pong", "t": 3}
            await device.start()
            await device.stop(frames=15)
            await device.idle()
    assert "unknown_type" in capsys.readouterr().out


async def test_healthz_reports_wake():
    async with gateway(wake=True) as (_, _, client, _, reply_base):
        async with client.get(reply_base + "/healthz") as response:
            body = await response.json()
            assert body["wake"] is True and body["version"] == "1.1.0"
