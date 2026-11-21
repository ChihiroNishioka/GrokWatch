import re

from pytest import fixture


REQUIRED_STRINGS = (
    "GROKWATCH_WIFI_SSID", "GROKWATCH_WIFI_PASSWORD", "GROKWATCH_GATEWAY_HOST", "GROKWATCH_DEVICE_TOKEN",
)


@fixture
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


def test_no_flash_erase_calls(firmware_sources):
    writes = re.compile(r"\b(?:\w*flash_\w*erase\w*|esp_partition_erase_range|nvs_(?:set_\w+|erase_\w+|commit))\s*\(")
    opens = []
    for path, source in firmware_sources.items():
        assert not writes.search(source), path
        opens.extend(re.findall(r"\bnvs_open(?:_from_partition)?\s*\(([^;]*)\)", source))
    assert opens
    assert all(re.search(r",\s*NVS_READONLY\s*,", args) for args in opens)


def test_no_secret_logging(firmware_sources):
    for path, source in firmware_sources.items():
        for call in re.findall(r"\bESP_LOG[A-Z_]+\s*\((.*?);", source, re.DOTALL):
            assert not re.search(r"\b\w*(?:password|token|ssid)\w*\b", call, re.IGNORECASE), path
