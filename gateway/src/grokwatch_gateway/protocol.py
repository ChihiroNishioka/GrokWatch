import json

from aiohttp import WSMsgType


FRAME_BYTES = 640
MAX_FRAMES = 750
MIN_FRAMES = 15
MAX_TEXT_BYTES = 4096

_FIELDS = {
    "hello": {"v": int, "token": str, "fw": str},
    "hello_ok": {"v": int},
    "auth_error": {"code": str},
    "listen_start": {},
    "listen_stop": {},
    "cancel": {},
    "state": {"state": str},
    "tts_start": {"sample_rate": int},
    "tts_end": {},
    "error": {"code": str, "retryable": bool},
    "ping": {"t": int},
    "pong": {"t": int},
}


def decode(frame):
    if frame.type != WSMsgType.TEXT:
        return None
    try:
        if len(frame.data.encode("utf-8")) > MAX_TEXT_BYTES:
            return None
        data = json.loads(frame.data)
        if not isinstance(data, dict) or not isinstance(data.get("type"), str):
            return None
        for value in data.values():
            if type(value) not in (str, int, bool):
                return None
            if isinstance(value, str):
                value.encode("utf-8")
        if any(type(data.get(field)) is not kind for field, kind in _FIELDS.get(data["type"], {}).items()):
            return None
        return data
    except (ValueError, RecursionError):
        return None
