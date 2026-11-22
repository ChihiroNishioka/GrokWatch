import asyncio
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import wave


class SttError(Exception):
    pass


class TtsError(Exception):
    pass


class MockStt:
    def __init__(self, text="試験の発話です", delay=0, fail=False):
        self.text = text
        self.delay = delay
        self.fail = fail

    async def __call__(self, pcm):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise SttError()
        return self.text


class MockTts:
    async def __call__(self, text):
        pattern = sha256(text.encode("utf-8")).digest()
        return (pattern * (len(text) * 5 + 1))[:len(text) * 162]


async def run_audio_command(*args, timeout, error):
    launch = asyncio.create_task(asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    ))
    process = None
    try:
        async with asyncio.timeout(timeout):
            process = await asyncio.shield(launch)
            if await process.wait():
                raise error()
    except (OSError, TimeoutError, ValueError):
        raise error() from None
    finally:
        if process is None:
            with suppress(OSError, ValueError):
                process = await launch
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()


class WhisperCpp:
    def __init__(self, model, executable="whisper-cli", timeout=30):
        self.model = model
        self.executable = executable
        self.timeout = timeout

    async def __call__(self, pcm):
        try:
            with TemporaryDirectory(prefix="grokwatch-stt-") as directory:
                source = Path(directory) / "speech.wav"
                with wave.open(str(source), "wb") as audio:
                    audio.setparams((1, 2, 16000, 0, "NONE", ""))
                    audio.writeframes(pcm)
                await run_audio_command(self.executable, "-m", self.model, "-f", str(source),
                                        "-l", "ja", "-nt", "-otxt", timeout=self.timeout, error=SttError)
                return source.with_suffix(".wav.txt").read_text(encoding="utf-8").strip()
        except (OSError, ValueError, wave.Error):
            raise SttError() from None


class MacosSay:
    def __init__(self, voice="Kyoko", timeout=30):
        self.voice = voice
        self.timeout = timeout

    async def __call__(self, text):
        try:
            with TemporaryDirectory(prefix="grokwatch-tts-") as directory:
                source = Path(directory) / "speech.txt"
                output = Path(directory) / "speech.wav"
                source.write_text(text, encoding="utf-8")
                await run_audio_command("say", "-v", self.voice, "-f", str(source), "--file-format=WAVE",
                                        "--data-format=LEI16@16000", "-o", str(output),
                                        timeout=self.timeout, error=TtsError)
                with wave.open(str(output), "rb") as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                        raise TtsError()
                    pcm = audio.readframes(audio.getnframes())
                    if len(pcm) != audio.getnframes() * 2:
                        raise TtsError()
                    return pcm
        except (EOFError, OSError, ValueError, wave.Error):
            raise TtsError() from None
