import hashlib
import hmac
import json
import re
from dataclasses import replace
from uuid import UUID

from aiohttp import web
from grokwatch_bridge.contract import ReplyChunk
from grokwatch_bridge.signing import signature


_BODY_LIMIT = 8192
_TIMESTAMP = re.compile(r"[+-]?[0-9]{1,32}")
_SIGNATURE = re.compile(r"sha256=[a-fA-F0-9]{64}")
_URL = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>\[\]{}()。！？、：；」』））》〉】]+"
)
_MARKDOWN = re.compile(r"[*_`~#>\[\](){}|\\]")
_KEYCAP = re.compile(r"[#*0-9]\ufe0f?\u20e3")
_EMOJI_PRESENTATION = re.compile(r"[^\s]\ufe0f")
_EMOJI_CHAR = re.compile(
    r"[\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\U0001f000-\U0001faff]"
)
_EMOTIONS = {"neutral", "happy", "sad", "surprised", "thinking"}
_URL_ENDING = ".,!?;:，。！？、」』）)]}"
_EMOJI_JOINERS = {"\ufe0e", "\ufe0f", "\u200d", "\u20e3"}


def valid_id(value):
    try:
        return str(UUID(value, version=4)) == value.lower()
    except ValueError:
        return False


def parse_reply(raw, request_id):
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or type(data.get("v")) is not int or data["v"] != 1:
            return None
        if data.get("request_id") != request_id:
            return None
        status, text = data.get("status"), data.get("text")
        emotion, end = data.get("emotion", "neutral"), data.get("end_conversation", False)
        if status not in ("ok", "declined", "error") or not isinstance(text, str) or len(text) > 400:
            return None
        if not isinstance(emotion, str) or not isinstance(end, bool):
            return None
        text.encode("utf-8")
        return ReplyChunk(text, status, emotion if emotion in _EMOTIONS else "neutral", end_conversation=end)
    except (ValueError, RecursionError):
        return None


def clean_speech_text(text):
    def replace_url(match):
        value = match.group()
        trimmed = value.rstrip(_URL_ENDING)
        return "リンク" + value[len(trimmed):]

    text = re.sub(r"(?m)^\s*(?:-\s*){3,}\s*$", "", text)
    text = re.sub(r"(?m)^\s*(?:[-+]|\d+[.)])\s+", "", text)
    text = _URL.sub(replace_url, text)
    text = _MARKDOWN.sub("", text)
    text = _KEYCAP.sub("", text)
    text = _EMOJI_PRESENTATION.sub("", text)
    text = "".join(
        "" if _EMOJI_CHAR.fullmatch(char) or char in _EMOJI_JOINERS
        or 0xE0020 <= ord(char) <= 0xE007F else char
        for char in text
    )
    return re.sub(r"\s+", " ", text).strip()


def reply_handler(registry, clock, log):
    async def receive(request):
        started = clock()

        def response(http_status, *, request_id=None, state=None, outcome=None, reply=None):
            log("reply", request_id=request_id, state=state, http_status=http_status,
                latency_ms=max(0, round((clock() - started) * 1000)),
                chars=len(reply.text) if reply else None,
                emotion=reply.emotion if reply else None, text=reply.text if reply else None)
            if outcome is not None:
                return web.json_response({"status": outcome})
            return web.Response(status=http_status)

        encodings = [
            encoding.strip().lower()
            for value in request.headers.getall("Content-Encoding", ())
            for encoding in value.split(",")
        ]
        if any(encoding != "identity" for encoding in encodings):
            return response(415)

        raw = bytearray()
        async for part in request.content.iter_chunked(_BODY_LIMIT + 1):
            raw.extend(part)
            if len(raw) > _BODY_LIMIT:
                return response(413)
        raw = bytes(raw)
        request_id = request.headers.get("X-GrokWatch-Request-Id", "")
        ts = request.headers.get("X-GrokWatch-Timestamp", "")
        signed = request.headers.get("X-GrokWatch-Signature", "")
        if (request.content_type != "application/json" or not valid_id(request_id)
                or not _TIMESTAMP.fullmatch(ts) or not _SIGNATURE.fullmatch(signed)):
            return response(422)

        # No await between looking up the entry and committing its terminal state.
        entry = registry.get(request_id)
        if entry is None:
            return response(404, request_id=request_id)
        fields = dict(request_id=request_id, state=entry.state)
        now = clock()
        if entry.state in {"cancelled", "expired"} or now >= entry.expires_at:
            return response(410, **fields)
        if abs(now - int(ts)) > 120:
            return response(401, **fields)
        if not hmac.compare_digest(signature(entry.token, ts, raw), signed.lower()):
            return response(401, **fields)
        digest = hashlib.sha256(raw).digest()
        if entry.state == "answered":
            if digest == entry.digest:
                return response(200, **fields, outcome="duplicate")
            return response(409, **fields)
        if (reply := parse_reply(raw, request_id)) is None:
            return response(422, **fields)
        cleaned_text = clean_speech_text(reply.text)
        if not cleaned_text:
            return response(422, **fields)
        reply = replace(reply, text=cleaned_text)
        registry.accept(entry, digest, reply)
        return response(200, request_id=request_id, state="answered", outcome="accepted", reply=reply)

    return receive
