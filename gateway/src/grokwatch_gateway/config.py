from dataclasses import dataclass, field
import math
import os
import subprocess


LOOPBACK = "127.0.0.1"


def read_secret(env, account):
    if env.get("GROKWATCH_ALLOW_ENV_SECRETS") == "1" and account in env:
        return env[account]
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "grokwatch", "-a", account, "-w"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8", timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return ""
    return result.stdout.rstrip("\r\n") if result.returncode == 0 else ""


@dataclass(frozen=True, slots=True)
class Config:
    device_token: str = field(repr=False)
    gateway_host: str = ""  # Empty selects the IPv4 wildcard at startup.
    gateway_port: int = 8765
    reply_host: str = LOOPBACK
    reply_port: int = 8767
    reply_timeout: float = 90
    hello_timeout: float = 5
    idle_timeout: float = 30
    ws_connection_limit: int = 4
    retention: float = 600
    bridge_name: str = "webhook"
    webhook_url: str = field(default="", repr=False)
    webhook_allow_loopback_http: bool = False
    webhook_key: str = field(default="", repr=False)
    agent_id: str = field(default="", repr=False)
    gbot_bin: str = "gbot"
    gbot_args: str = field(default="[]", repr=False)
    mock_mode: str = "fixed"
    mock_text: str = "試験の返事です"
    mock_delay: float = 0
    mock_variant: str = "normal"
    mock_status: str = "ok"
    mock_end: bool = False
    stt_name: str = "mock"
    stt_text: str = "試験の発話です"
    stt_delay: float = 0
    stt_fail: bool = False
    tts_name: str = "mock"
    whisper_bin: str = "whisper-cli"
    whisper_model: str = ""
    tts_voice: str = "Kyoko"
    log_text: bool = False
    extra_redactions: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self):
        if len(self.device_token) < 32:
            raise ValueError("A device token of at least 32 characters is required")
        if self.ws_connection_limit < 1:
            raise ValueError("WebSocket connection limit must be positive")
        if self.reply_host != LOOPBACK:
            raise ValueError("The reply listener requires IPv4 loopback")
        if any(not 0 <= port <= 65535 for port in (self.gateway_port, self.reply_port)):
            raise ValueError("Port outside the supported range")
        if any(not math.isfinite(seconds) or seconds <= 0 for seconds in (
            self.reply_timeout, self.hello_timeout, self.idle_timeout, self.retention,
        )):
            raise ValueError("Timeouts and retention must be finite and positive")
        if self.bridge_name not in {"webhook", "gbot_cli", "mock"}:
            raise ValueError("Invalid GROKWATCH_BRIDGE")
        if self.stt_name not in {"mock", "whisper_cpp"} or self.tts_name not in {"mock", "macos_say"}:
            raise ValueError("Invalid STT or TTS provider")
        if self.stt_name == "whisper_cpp" and not self.whisper_model:
            raise ValueError("GROKWATCH_WHISPER_MODEL is required")
        if any(not math.isfinite(seconds) or seconds < 0 for seconds in (self.mock_delay, self.stt_delay)):
            raise ValueError("Mock delays must be finite and nonnegative")

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env

        def get(key, default=""):
            return env.get("GROKWATCH_" + key, default)

        def number(key, default, cast=float):
            try:
                return cast(get(key, default))
            except ValueError:
                raise ValueError("Invalid numeric setting GROKWATCH_" + key) from None

        reply_host, sep, reply_port = get("REPLY_LISTEN", LOOPBACK + ":8767").partition(":")
        if not sep or not reply_port.isascii() or not reply_port.isdecimal():
            raise ValueError("Invalid GROKWATCH_REPLY_LISTEN")

        bridge_name = get("BRIDGE", "webhook")
        return cls(
            device_token=read_secret(env, "GROKWATCH_DEVICE_TOKEN"),
            gateway_host=get("GATEWAY_HOST"), gateway_port=number("GATEWAY_PORT", "8765", int),
            reply_host=reply_host, reply_port=int(reply_port), reply_timeout=number("REPLY_TIMEOUT_S", "90"),
            ws_connection_limit=number("WS_CONNECTION_LIMIT", "4", int),
            bridge_name=bridge_name,
            webhook_allow_loopback_http=get("WEBHOOK_ALLOW_LOOPBACK_HTTP") == "1",
            webhook_url=read_secret(env, "GROKWATCH_WEBHOOK_URL") if bridge_name == "webhook" else "",
            webhook_key=read_secret(env, "GROKWATCH_WEBHOOK_KEY") if bridge_name == "webhook" else "",
            agent_id=get("AGENT_ID"), gbot_bin=get("GBOT_BIN", "gbot"), gbot_args=get("GBOT_ARGS", "[]"),
            mock_mode=get("MOCK_MODE", "fixed"), mock_text=get("MOCK_REPLY", "試験の返事です"),
            mock_delay=number("MOCK_DELAY_S", "0"), mock_variant=get("MOCK_VARIANT", "normal"),
            mock_status=get("MOCK_STATUS", "ok"), mock_end=get("MOCK_END") == "1",
            stt_name=get("STT", "mock"), stt_text=get("MOCK_STT_TEXT", "試験の発話です"),
            stt_delay=number("MOCK_STT_DELAY_S", "0"), stt_fail=get("MOCK_STT_FAIL") == "1",
            tts_name=get("TTS", "mock"), whisper_bin=get("WHISPER_BIN", "whisper-cli"),
            whisper_model=get("WHISPER_MODEL"), tts_voice=get("TTS_VOICE", "Kyoko"),
            log_text=get("LOG_TEXT") == "1",
        )

    def bridge_env(self):
        return {
            "GROKWATCH_BRIDGE": self.bridge_name, "GROKWATCH_REPLY_TIMEOUT_S": str(self.reply_timeout),
            "GROKWATCH_WEBHOOK_URL": self.webhook_url, "GROKWATCH_WEBHOOK_KEY": self.webhook_key,
            "GROKWATCH_WEBHOOK_ALLOW_LOOPBACK_HTTP": str(int(self.webhook_allow_loopback_http)),
            "GROKWATCH_GBOT_BIN": self.gbot_bin, "GROKWATCH_GBOT_ARGS": self.gbot_args,
            "GROKWATCH_AGENT_ID": self.agent_id, "GROKWATCH_MOCK_MODE": self.mock_mode,
            "GROKWATCH_MOCK_REPLY": self.mock_text, "GROKWATCH_MOCK_DELAY_S": str(self.mock_delay),
            "GROKWATCH_MOCK_VARIANT": self.mock_variant, "GROKWATCH_MOCK_STATUS": self.mock_status,
            "GROKWATCH_MOCK_END": str(int(self.mock_end)),
        }
