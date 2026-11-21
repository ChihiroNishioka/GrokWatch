import asyncio
import json
import secrets
from urllib.parse import urlsplit

import pytest

from support import connected, gateway


@pytest.mark.parametrize("switch", [None, "0", "1"])
async def test_log_text_toggle(monkeypatch, capsys, switch):
    if switch is None:
        monkeypatch.delenv("GROKWATCH_LOG_TEXT", raising=False)
    else:
        monkeypatch.setenv("GROKWATCH_LOG_TEXT", switch)
    from grokwatch_gateway.config import Config
    env = {"GROKWATCH_DEVICE_TOKEN": secrets.token_urlsafe(32), "GROKWATCH_ALLOW_ENV_SECRETS": "1"}
    if switch is not None:
        env["GROKWATCH_LOG_TEXT"] = switch
    log_text = Config.from_env(env).log_text
    values = [secrets.token_urlsafe(32) for _ in range(5)]
    url = "http://127.0.0.1:1/" + secrets.token_urlsafe(8)
    identifiers = ("2001:db8::1", "::ffff:192.0.2.1", "fe80::1%test",
                   ":".join(("02", "00", "5e", "00", "53", "01")),
                   "-".join(("02", "00", "5e", "00", "53", "02")),
                   ".".join(("0200", "5e00", "5303")))
    phrase = "発話です"
    reply = "返事です"

    async def stt(pcm):
        return phrase + " " + " ".join([config.device_token, *values, url, "/private/test-note",
                                        "127.0.0.1", *identifiers])

    async with gateway(stt=stt, bridge_name="mock", mock_mode="post_reply", log_text=log_text,
                       webhook_key=values[0], webhook_url=url, agent_id=values[2],
                       extra_redactions=(values[1], values[3], values[4]), mock_text=reply) as (
        app, config, client, base, _,
    ):
        async with connected(client, base, config) as device:
            await device.start()
            await device.stop(pcm=b"UNIQUE" + b"x" * 634)
            await device.idle()
            await device.ws.send_str("{")
            await device.receive()
        result = capsys.readouterr().out
        rows = [json.loads(line) for line in result.splitlines()]
        assert rows and all({"event", "request_id", "latency_ms"} <= row.keys() for row in rows)
        assert all(value not in result for value in (
            *values, *identifiers, config.device_token, app.bridge.last_request.reply_token, url, "UNIQUE",
            "/private/test-note", "127.0.0.1",
        ))
        assert (phrase in result) == (switch == "1")
        assert (reply in result) == (switch == "1")
        if switch == "1":
            assert "***" in result


async def test_http_parser_errors_do_not_log_peer_or_request_data(caplog):
    async with gateway() as (_, _, _, base, _):
        caplog.clear()
        secret = secrets.token_urlsafe(18)
        address = urlsplit(base)
        reader, writer = await asyncio.open_connection(address.hostname, address.port)
        writer.write(
            b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nBad Header: "
            + secret.encode()
            + b"\r\n\r\n"
        )
        await writer.drain()
        await asyncio.wait_for(reader.read(), 1)
        writer.close()
        await writer.wait_closed()

        output = caplog.text
        assert "127.0.0.1" not in output and secret not in output, (
            "aiohttp logger exposed a peer or synthetic secret"
        )
