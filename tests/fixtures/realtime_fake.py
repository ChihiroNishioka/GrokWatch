import asyncio
import base64
from contextlib import asynccontextmanager
import json
import stat
import sys

from aiohttp import WSMsgType, web

from support import serve


def pcm24(samples=2400, value=1000):
    return value.to_bytes(2, "little", signed=True) * samples


def delta(samples=2400):
    return {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm24(samples)).decode()}


def done(*calls):
    output = [{"type": "function_call", "name": name, "call_id": call_id, "arguments": json.dumps(args)}
              for name, call_id, args in calls]
    return {"type": "response.done", "response": {"status": "completed", "output": output}}


SPEECH = [delta(), delta(), {"type": "response.output_audio.done"}, done()]


class FakeRealtime:
    """Scripted OpenAI Realtime server. Each response.create consumes one script.

    A script is a list of events (dicts), "close" (drop the connection) or a number (seconds to wait).
    """

    def __init__(self, scripts=()):
        self.scripts = list(scripts)
        self.received = []
        self.connections = 0
        self.open = 0
        self.headers = []
        self.queries = []

    def events(self, kind):
        return [event for event in self.received if event.get("type") == kind]

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        self.open += 1
        self.headers.append(dict(request.headers))
        self.queries.append(dict(request.query))
        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                event = json.loads(message.data)
                self.received.append(event)
                if event["type"] == "response.create":
                    for item in (self.scripts.pop(0) if self.scripts else SPEECH):
                        if item == "close":
                            await ws.close()
                            return ws
                        if isinstance(item, (int, float)):
                            await asyncio.sleep(item)
                        else:
                            await ws.send_json(item)
        finally:
            self.open -= 1
        return ws

    @asynccontextmanager
    async def serve(self):
        app = web.Application()
        app.router.add_get("/v1/realtime", self.handler)
        async with serve(app) as base:
            yield base.replace("http://", "ws://", 1) + "/v1/realtime"


class FakeHttp:
    """Fake Responses API and task webhook."""

    def __init__(self, status=200, text="明日は晴れです。"):
        self.status = status
        self.text = text
        self.search = []
        self.tasks = []

    async def responses(self, request):
        self.search.append((dict(request.headers), await request.json()))
        body = {"output": [{"type": "web_search_call"},
                           {"type": "message", "content": [{"type": "output_text", "text": self.text}]}]}
        return web.json_response(body, status=self.status)

    async def task(self, request):
        self.tasks.append((dict(request.headers), await request.json()))
        return web.json_response({}, status=self.status)

    @asynccontextmanager
    async def serve(self):
        app = web.Application()
        app.router.add_post("/v1/responses", self.responses)
        app.router.add_post("/task", self.task)
        async with serve(app) as base:
            yield base


def make_helper(path, *, exit_code=0, delay=0, schedule=None, mail=None):
    """Write an executable fake grokwatch-context that logs its arguments to <path>.log."""
    config = path.with_suffix(".json")
    config.write_text(json.dumps(dict(exit=exit_code, delay=delay, schedule=schedule, mail=mail)))
    path.write_text(f"""#!{sys.executable}
import json, sys, time
cfg = json.load(open({str(config)!r}))
open({str(path) + '.log'!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")
time.sleep(cfg["delay"])
if cfg["exit"]:
    sys.exit(cfg["exit"])
if sys.argv[1] == "schedule":
    print(json.dumps(cfg["schedule"] or {{"events": [{{"title": "会議", "start": "2026-11-22T10:00:00+09:00", "end": "2026-11-22T11:00:00+09:00", "all_day": False, "location": "A室", "calendar": "仕事"}}]}}))
else:
    print(json.dumps(cfg["mail"] or {{"messages": [{{"from": "田中", "subject": "資料の件", "received": "2026-11-22T08:00:00+09:00"}}]}}))
""")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def helper_calls(path):
    log = path.with_name(path.name + ".log")
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
