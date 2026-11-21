import hmac


def signature(reply_token: str, timestamp: str, body: bytes) -> str:
    digest = hmac.digest(reply_token.encode("utf-8"), timestamp.encode("ascii") + b"." + body, "sha256")
    return "sha256=" + digest.hex()
