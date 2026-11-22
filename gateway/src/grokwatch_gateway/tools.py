import asyncio
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
import json
import os
import re
from uuid import uuid4

import aiohttp
from grokwatch_bridge.webhook import encode_body, validate_url


JST = timezone(timedelta(hours=9), "JST")
CACHE_SECONDS = 300
TIMEOUTS = {"get_schedule": 3, "get_mail": 3, "web_search": 10, "delegate_to_grok_bot": 5}
# The background warm-up may wait longer: Mail.app scripting can take several seconds on a large inbox.
REFRESH_TIMEOUT = 20
MAX_EVENTS = 30
MAX_MESSAGES = 20
MAX_HELPER_BYTES = 262144
MAX_SEARCH_CHARS = 800
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_EVENT_FIELDS = ("title", "start", "end", "all_day", "location", "calendar")
_MAIL_FIELDS = ("from", "subject", "received")

TOOL_DEFINITIONS = [
    {
        "type": "function", "name": "get_schedule",
        "description": "オーナーのカレンダーの予定を調べる。日付は YYYY-MM-DD（日本時間）。省略すると今日から明日まで。",
        "parameters": {"type": "object", "properties": {
            "from": {"type": "string", "description": "開始日 YYYY-MM-DD"},
            "to": {"type": "string", "description": "終了日 YYYY-MM-DD"},
        }},
    },
    {
        "type": "function", "name": "get_mail",
        "description": "オーナーのメールの差出人・件名・受信日時を調べる（本文は読めない）。",
        "parameters": {"type": "object", "properties": {
            "unread_only": {"type": "boolean", "description": "未読だけ（既定 true）"},
            "since_hours": {"type": "integer", "description": "何時間前から（既定 24）"},
            "limit": {"type": "integer", "description": "最大件数（既定 10）"},
        }},
    },
    {
        "type": "function", "name": "web_search",
        "description": "最新のニュースや天気など、Web で調べないと分からないことを調べて要約を返す。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "調べたいこと"},
        }, "required": ["query"]},
    },
    {
        "type": "function", "name": "delegate_to_grok_bot",
        "description": "調べもの・整理・下書きなどの作業を Grok Bot に頼む。送信・削除・購入・支払い・予約の確定は頼まない。",
        "parameters": {"type": "object", "properties": {
            "request": {"type": "string", "description": "依頼内容を日本語で具体的に"},
        }, "required": ["request"]},
    },
]


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clamp(value, default, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(low, min(high, int(value)))


class ToolError(Exception):
    def __init__(self, code):
        self.code = code


class Tools:
    def __init__(self, config, log, clock):
        self.config = config
        self.log = log
        self.clock = clock
        self.cache = {}
        self.inflight = {}

    def today(self):
        return datetime.fromtimestamp(self.clock(), JST).date()

    async def call(self, name, arguments):
        started = self.clock()
        count = None
        try:
            args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else {}
            if not isinstance(args, dict):
                raise ValueError()
        except ValueError:
            args = None
        handler = {
            "get_schedule": self.get_schedule, "get_mail": self.get_mail,
            "web_search": self.web_search, "delegate_to_grok_bot": self.delegate,
        }.get(name)
        try:
            if handler is None:
                raise ToolError("unknown_tool")
            if args is None:
                raise ToolError("bad_arguments")
            async with asyncio.timeout(TIMEOUTS[name]):
                result = await handler(args)
            code = None
            count = result.get("count")
            body = {key: value for key, value in result.items() if key != "count"}
        except ToolError as error:
            code, body = error.code, {"error": error.code}
        except TimeoutError:
            code, body = "timeout", {"error": "timeout"}
        except Exception:
            code, body = "failed", {"error": "failed"}
        self.log("tool_call", tool=name if handler else "unknown", code=code, count=count,
                 level="info" if code is None else "warning",
                 latency_ms=max(0, round((self.clock() - started) * 1000)))
        return encode(body)

    async def refresh(self):
        """Warm the cache for the default queries. Errors are ignored.

        Runs with REFRESH_TIMEOUT rather than the tool timeout, so a slow helper still fills the cache;
        a tool call made meanwhile joins the in-flight run (see fetch)."""
        for handler in (self.get_schedule, self.get_mail):
            with suppress(Exception):
                async with asyncio.timeout(REFRESH_TIMEOUT):
                    await handler({})

    async def fetch(self, key, build, *command):
        """Run the helper once per key at a time; concurrent callers share the same run.

        The shared run builds and caches the result itself, so it still fills the cache when the
        caller that started it gave up (tool timeout)."""
        async def run():
            async with asyncio.timeout(REFRESH_TIMEOUT):  # hard cap: a hung helper is killed
                data = await self.run_helper(*command)
            result = build(data)
            self.store(key, result)
            return result

        task = self.inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(run())
            self.inflight[key] = task
            task.add_done_callback(lambda done, key=key: (self.inflight.pop(key, None),
                                                          done.cancelled() or done.exception()))
        return await asyncio.shield(task)

    def cached(self, key):
        entry = self.cache.get(key)
        if entry and self.clock() < entry[0]:
            return entry[1]
        return None

    def store(self, key, value):
        now = self.clock()
        self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
        self.cache[key] = (now + CACHE_SECONDS, value)

    async def get_schedule(self, args):
        today = self.today()
        try:
            start = self.parse_date(args.get("from"), today)
            end = self.parse_date(args.get("to"), start + timedelta(days=1))
        except ValueError:
            raise ToolError("bad_arguments") from None
        if end < start:
            raise ToolError("bad_arguments")
        key = ("schedule", start, end)
        if (hit := self.cached(key)) is not None:
            return hit
        def build(data):
            events = [{field: item.get(field) for field in _EVENT_FIELDS if field in item}
                      for item in data.get("events", []) if isinstance(item, dict)][:MAX_EVENTS]
            return {"events": events, "count": len(events)}
        return await self.fetch(key, build, "schedule", "--from", start.isoformat(), "--to", end.isoformat())

    async def get_mail(self, args):
        unread = args.get("unread_only", True)
        unread = unread if isinstance(unread, bool) else True
        hours = clamp(args.get("since_hours"), 24, 1, 168)
        limit = clamp(args.get("limit"), 10, 1, MAX_MESSAGES)
        key = ("mail", unread, hours, limit)
        if (hit := self.cached(key)) is not None:
            return hit
        command = ["mail", "--since-hours", str(hours), "--limit", str(limit)]
        if unread:
            command.append("--unread-only")
        def build(data):
            messages = [{field: item.get(field) for field in _MAIL_FIELDS if field in item}
                        for item in data.get("messages", []) if isinstance(item, dict)][:limit]
            return {"messages": messages, "count": len(messages)}
        return await self.fetch(key, build, *command)

    @staticmethod
    def parse_date(value, default):
        if value in (None, ""):
            return default
        if not isinstance(value, str) or not _DATE.fullmatch(value):
            raise ValueError()
        return date.fromisoformat(value)

    async def run_helper(self, *args):
        binary = os.path.expandvars(os.path.expanduser(self.config.context_bin))
        launch = asyncio.create_task(asyncio.create_subprocess_exec(
            binary, *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        ))
        process = None
        try:
            process = await asyncio.shield(launch)
            output, _ = await process.communicate()
            code = process.returncode
        except (OSError, ValueError):
            raise ToolError("unavailable") from None
        finally:
            if process is None:
                with suppress(OSError, ValueError):
                    process = await launch
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await asyncio.shield(process.wait())
        if code == 3:
            raise ToolError("permission_denied")
        if code == 4:
            raise ToolError("mail_not_running")
        if code != 0 or len(output) > MAX_HELPER_BYTES:
            raise ToolError("unavailable")
        try:
            data = json.loads(output)
        except ValueError:
            raise ToolError("unavailable") from None
        if not isinstance(data, dict):
            raise ToolError("unavailable")
        return data

    async def web_search(self, args):
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolError("bad_arguments")
        body = {
            "model": self.config.search_model, "tools": [{"type": "web_search"}],
            "input": query.strip()[:500] + "\n\n日本語で、2〜3文の短い要約で答えてください。URLや記号は使わないでください。",
        }
        headers = {"Authorization": "Bearer " + self.config.openai_api_key, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUTS["web_search"])) as client:
                async with client.post(self.config.responses_url, headers=headers, json=body,
                                       allow_redirects=False) as response:
                    if response.status != 200:
                        raise ToolError("unavailable")
                    data = await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            raise ToolError("unavailable") from None
        text = self.output_text(data)
        if not text:
            raise ToolError("unavailable")
        return {"summary": text[:MAX_SEARCH_CHARS], "count": 1}

    @staticmethod
    def output_text(data):
        if not isinstance(data, dict):
            return ""
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        parts = []
        for item in data.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        parts.append(part["text"])
        return "".join(parts).strip()

    async def delegate(self, args):
        request = args.get("request")
        if not isinstance(request, str) or not request.strip():
            raise ToolError("bad_arguments")
        url, key = self.config.task_webhook_url, self.config.task_webhook_key
        if not url or not key:
            return {"status": "not_configured"}
        validate_url(url, self.config.webhook_allow_loopback_http)
        payload = dict(v=1, type="task", request_id=str(uuid4()), text=request.strip()[:1000],
                       created_at=datetime.fromtimestamp(self.clock(), timezone.utc).isoformat())
        headers = {"Authorization": "Bearer " + key, "X-Automation-Key": key, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUTS["delegate_to_grok_bot"])) as client:
                async with client.post(url, headers=headers, data=encode_body(payload),
                                       allow_redirects=False) as response:
                    if 200 <= response.status < 300:
                        return {"status": "accepted"}
        except (aiohttp.ClientError, ValueError):
            pass
        return {"status": "failed"}
