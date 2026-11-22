import json
import os
import time

from .gbot_cli import GbotCli
from .mock import MockBridge
from .webhook import Webhook


def create_bridge(inbox, env=None, *, clock=time.time, gbot_timeout=60):
    env = os.environ if env is None else env
    name = env.get("GROKWATCH_BRIDGE", "webhook")
    timeout = float(env.get("GROKWATCH_REPLY_TIMEOUT_S", "90"))
    if name == "webhook":
        return Webhook(inbox, env.get("GROKWATCH_WEBHOOK_URL", ""), env.get("GROKWATCH_WEBHOOK_KEY", ""),
                       clock=clock, reply_timeout=timeout,
                       allow_loopback_http=env.get("GROKWATCH_WEBHOOK_ALLOW_LOOPBACK_HTTP") == "1")
    if name == "gbot_cli":
        try:
            args = json.loads(env.get("GROKWATCH_GBOT_ARGS", "[]"))
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError()
        except ValueError:
            raise ValueError("GROKWATCH_GBOT_ARGS must be a JSON array of strings") from None
        return GbotCli(env.get("GROKWATCH_GBOT_BIN", "gbot"), args,
                       env.get("GROKWATCH_AGENT_ID", ""), gbot_timeout)
    if name == "mock":
        return MockBridge(
            inbox, clock=clock, reply_timeout=timeout, mode=env.get("GROKWATCH_MOCK_MODE", "fixed"),
            text=env.get("GROKWATCH_MOCK_REPLY", "試験の返事です"),
            delay=float(env.get("GROKWATCH_MOCK_DELAY_S", "0")),
            variant=env.get("GROKWATCH_MOCK_VARIANT", "normal"),
            status=env.get("GROKWATCH_MOCK_STATUS", "ok"),
            end=env.get("GROKWATCH_MOCK_END", "0") == "1",
        )
    raise ValueError("GROKWATCH_BRIDGE must be webhook, gbot_cli, or mock")
