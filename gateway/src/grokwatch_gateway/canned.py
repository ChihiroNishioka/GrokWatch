from .audio import TtsError


CANNED_TEXT = {
    "bridge_unavailable": "いま伝書鳩につながらないみたい",
    "bridge_timeout": "ごめん、返事が来なかったみたい",
    "stt_failed": "うまく聞き取れなかったみたい",
    "reply_error": "ごめん、いまは答えられないみたい",
}


async def synthesize_canned(tts):
    cache = {}
    for code, text in CANNED_TEXT.items():
        try:
            cache[code] = await tts(text)
        except TtsError:
            pass
    return cache
