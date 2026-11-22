import asyncio
from contextlib import suppress
from dataclasses import dataclass
from ipaddress import IPv4Address
import logging
import time

from aiohttp import web
from grokwatch_bridge.factory import create_bridge
from grokwatch_bridge.mock import MockBridge

from .audio import MacosSay, MockStt, MockTts, WhisperCpp
from .canned import synthesize_canned
from .config import Config
from .logging import EventLog
from .registry import Registry
from .reply_server import reply_handler
from .ws_server import WebSocketServer


@dataclass(slots=True)
class Gateway:
    ws_app: web.Application
    reply_app: web.Application
    devices: WebSocketServer
    registry: Registry
    bridge: object

    @property
    def device_connected(self):
        return self.devices.active is not None

    def set_reply_url(self, url):
        if isinstance(self.bridge, MockBridge):
            self.bridge.reply_url = url


def create_gateway(config, *, stt=None, wake_stt=None, tts=None, bridge=None, clock=time.time, sleep=asyncio.sleep, pace_clock=time.monotonic):
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL + 1)
    registry = Registry(clock, config.retention)
    log = EventLog(log_text=config.log_text, tokens=registry.tokens, redactions=(
        config.device_token, config.webhook_key, config.webhook_url, config.agent_id,
        config.gateway_host, config.whisper_bin if "/" in config.whisper_bin else "",
        config.whisper_model, config.wake_model, config.gbot_bin if "/" in config.gbot_bin else "",
        *config.extra_redactions,
    ))
    if bridge is None:
        bridge = create_bridge(registry, config.bridge_env(), clock=clock)
    if stt is None:
        stt = (WhisperCpp(config.whisper_model, config.whisper_bin) if config.stt_name == "whisper_cpp"
               else MockStt(config.stt_text, config.stt_delay, config.stt_fail))
    if wake_stt is None:
        wake_stt = (WhisperCpp(config.wake_model or config.whisper_model, config.whisper_bin)
                    if config.stt_name == "whisper_cpp" else stt)
    if tts is None:
        tts = MacosSay(config.tts_voice) if config.tts_name == "macos_say" else MockTts()

    canned = {}
    devices = WebSocketServer(config, stt, tts, bridge, canned, log, clock, sleep, pace_clock, wake_stt)
    ws_app = web.Application()
    reply_app = web.Application(handler_args={"auto_decompress": False})
    gateway = Gateway(ws_app, reply_app, devices, registry, bridge)

    async def startup(app):
        canned.update(await synthesize_canned(tts))

    async def maintain_registry(app):
        async def sweep():
            while True:
                await asyncio.sleep(1)
                registry.sweep()

        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def health(request):
        bridge_health = await bridge.health()
        return web.json_response(dict(
            status="ok" if bridge_health.available else "degraded",
            bridge=dict(name=bridge.name, available=bridge_health.available),
            stt=config.stt_name, tts=config.tts_name,
            device_connected=gateway.device_connected, wake=config.wake, version="1.1.0",
        ))

    ws_app.on_startup.append(startup)
    ws_app.on_shutdown.append(devices.shutdown)
    ws_app.router.add_get("/v1/ws", devices.handle)
    reply_app.cleanup_ctx.append(maintain_registry)
    reply_app.router.add_post("/v1/reply", reply_handler(registry, clock, log))
    reply_app.router.add_get("/healthz", health)
    return gateway


async def run(config):
    gateway = create_gateway(config)
    reply = web.AppRunner(gateway.reply_app, access_log=None, handle_signals=True)
    device = web.AppRunner(gateway.ws_app, access_log=None, shutdown_timeout=1)
    try:
        await reply.setup()
        await web.TCPSite(reply, config.reply_host, config.reply_port).start()
        port = reply.addresses[0][1]
        gateway.set_reply_url(f"http://{config.reply_host}:{port}/v1/reply")
        await device.setup()
        await web.TCPSite(device, config.gateway_host or str(IPv4Address(0)), config.gateway_port).start()
        await asyncio.Future()
    finally:
        await device.cleanup()
        await reply.cleanup()


def main():
    log = EventLog()
    try:
        asyncio.run(run(Config.from_env()))
    except (KeyboardInterrupt, web.GracefulExit):
        return
    except (ValueError, OSError):
        log("startup_failed", level="error", code="configuration_or_listener")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
