import re
import unicodedata


DEFAULT_PATTERN = (
    "(ハイ|ヘイ|ハーイ|ネエ|ネー|hi|hey|ok|オーケー)"
    "(グロック|グロク|グロッグ|グロッ?ク|grok|grock|groq|groc)"
)


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char
        for char in text
        if unicodedata.category(char)[0] not in "ZPSC" or char == "ー"
    )


def compile_pattern(pattern=""):
    return re.compile(pattern or DEFAULT_PATTERN, re.IGNORECASE)


def is_wake(text, pattern=None):
    if not isinstance(pattern, re.Pattern):
        pattern = compile_pattern(pattern or "")
    return pattern.search(normalize(text)) is not None
