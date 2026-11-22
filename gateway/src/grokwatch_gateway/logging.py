from datetime import datetime, timezone
import json
import re


_SENSITIVE_TEXT = re.compile(
    r"(?:https?|wss?)://[^\s]+|sha256=[0-9a-fA-F]{64}|"
    r"(?i:(?<![\w:])(?:[a-f0-9]{2}[:-]){5}[a-f0-9]{2}(?![\w:]))|"
    r"(?i:(?<![\w.])(?:[a-f0-9]{4}\.){2}[a-f0-9]{4}(?![\w.]))|"
    r"(?i:(?<![\w:])(?:[a-f0-9]{0,4}:){2,}(?:[a-f0-9]{0,4})"
    r"(?:\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})?(?:%[\w.-]+)?(?![\w:]))|"
    r"(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.])|"
    r"(?<![\w.])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![\w.])|"
    r"(?<!\w)/(?:[^\s/]+/)*[^\s/]+"
)


class EventLog:
    def __init__(self, *, log_text=False, redactions=(), tokens=lambda: ()):
        self.log_text = log_text
        self.redactions = frozenset(value for value in redactions if value)
        self.tokens = tokens

    def __call__(self, event, *, level="info", request_id=None, state=None, http_status=None,
                 latency_ms=None, chars=None, code=None, emotion=None, text=None, hit=None, frames=None,
                 count=None, tool=None):
        record = dict(ts=datetime.now(timezone.utc).isoformat(), level=level, event=event,
                      request_id=request_id, state=state, http_status=http_status,
                      latency_ms=latency_ms, chars=chars, code=code)
        if emotion is not None:
            record["emotion"] = emotion
        if hit is not None:
            record["hit"] = hit
        if frames is not None:
            record["frames"] = frames
        if count is not None:
            record["count"] = count
        if tool is not None:
            record["tool"] = tool
        if self.log_text and text is not None:
            record["text"] = text
        redactions = sorted(self.redactions.union(self.tokens()), key=len, reverse=True)
        for key, value in record.items():
            if isinstance(value, str):
                if key == "text":
                    value = _SENSITIVE_TEXT.sub("***", value)
                for secret in redactions:
                    value = value.replace(secret, "***")
                record[key] = value
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), flush=True)
