import asyncio
import re
import secrets
from urllib.error import HTTPError

from aiohttp import web
import pytest

from support import serve


REQUIRED_STRINGS = (
    "GROKWATCH_WIFI_SSID", "GROKWATCH_WIFI_PASSWORD", "GROKWATCH_GATEWAY_HOST", "GROKWATCH_DEVICE_TOKEN",
)


@pytest.fixture
def firmware_sources(repo_root):
    firmware = repo_root / "firmware"
    sources = [p for base in ("main", "components") for p in (firmware / base).rglob("*")
               if p.suffix in {".c", ".h", ".cpp", ".hpp"}]
    assert sources
    return {path: path.read_text() for path in sources}


def test_no_secret_defaults(repo_root):
    firmware = repo_root / "firmware"
    kconfig = (firmware / "main/Kconfig.projbuild").read_text()
    sdkconfig = (firmware / "sdkconfig.defaults").read_text()
    for key in REQUIRED_STRINGS:
        block = re.search(rf"^config {key}\s*\n((?:[ \t]+[^\n]*\n)*)", kconfig, re.MULTILINE)
        assert block, key
        assert re.findall(r"^\s*default (.+)$", block[1], re.MULTILINE) == ['""'], key
        assert all(value == '""' for value in re.findall(rf"^CONFIG_{key}=(.*)$", sdkconfig, re.MULTILINE)), key


def test_no_nvs_or_flash_mutation_calls(firmware_sources):
    prohibited = re.compile(
        r"\b(?:nvs_\w+|\w*flash_\w*erase\w*|"
        r"(?:esp_partition|spi_flash|esp_flash)_(?:erase|write)\w*)\s*\("
    )
    for path, source in firmware_sources.items():
        assert not prohibited.search(source), path


def test_no_secret_logging(firmware_sources):
    for path, source in firmware_sources.items():
        for call in re.findall(r"\bESP_LOG[A-Z_]+\s*\((.*?);", source, re.DOTALL):
            assert not re.search(r"\b\w*(?:password|token|ssid)\w*\b", call, re.IGNORECASE), path


def test_no_address_logging(firmware_sources):
    prohibited = re.compile(
        r"\b(?:config|config_|IP2STR|IPSTR|ip_info|esp_ip4addr_ntoa|MACSTR|bssid|ssid|"
        r"password|token|host|port|target_bytes)\b|\.(?:host|port)\b",
        re.IGNORECASE,
    )
    for path, source in firmware_sources.items():
        for call in re.findall(r"\bESP_LOG[A-Z_]+\s*\((.*?);", source, re.DOTALL):
            assert not prohibited.search(call), path


def test_log_formats_allowlisted(repo_root):
    net = (repo_root / "firmware/main/net_task.cpp").read_text()
    buttons = (repo_root / "firmware/main/button_task.cpp").read_text()
    formats = set(re.findall(r'ESP_LOG[A-Z_]+\([^\n]*?"((?:diag|volume)[^"\n]*)"', net + buttons))
    assert formats == {
        "diag wifi: associated",
        "diag wifi: disconnected reason=%d",
        "diag wifi: got ip",
        "diag scan: failed",
        "diag scan: non-ascii ap ch=%u",
        "diag scan: target found ch=%u auth=%d rssi=%d",
        "diag scan: aps=%u non_ascii=%d target_found=%d",
        "diag ws: connecting",
        "diag ws: connected",
        "diag ws: error",
        "diag ws: disconnected",
        "volume value=%u",
    }


async def test_documented_reply_sender_rejects_redirect(repo_root):
    namespace = {}
    document = (repo_root / "docs/BRIDGE_WEBHOOK.md").read_text()
    script = document.split("```python\n", 1)[1].split("```", 1)[0]
    exec(script, namespace)
    arrivals = []

    async def target(request):
        arrivals.append(request.method)
        return web.Response()

    async def redirect(request):
        raise web.HTTPFound("/target")

    app = web.Application()
    app.router.add_post("/v1/reply", redirect)
    app.router.add_route("*", "/target", target)
    async with serve(app) as base:
        with pytest.raises(HTTPError) as error:
            await asyncio.to_thread(namespace["send_reply"], base, "fixture", secrets.token_urlsafe(32), "返事")
        assert error.value.code == 302
    assert not arrivals
