import os
from pathlib import Path
import sys
import time
import wave
import json

name, *args = sys.argv[1:]
root = Path(os.environ["GW_FIXTURE_DIR"])
prefix = "GW_FIXTURE_" + name.upper().replace("-", "_")
(root / (name + ".json")).write_text(json.dumps(args))
(root / (name + ".pid")).write_text(str(os.getpid()))
time.sleep(float(os.getenv(prefix + "_DELAY", "0")))
if code := int(os.getenv(prefix + "_EXIT", "0")):
    sys.exit(code)
text = os.getenv(prefix + "_TEXT", "試験")
if name == "whisper-cli":
    source = Path(args[args.index("-f") + 1])
    with wave.open(str(source), "rb") as audio:
        (root / "whisper.wav.json").write_text(json.dumps(
            [audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()]
        ))
    source.with_suffix(".wav.txt").write_text(text)
elif name == "say":
    source = Path(args[args.index("-f") + 1])
    (root / "say.input").write_text(source.read_text())
    with wave.open(args[args.index("-o") + 1], "wb") as audio:
        channels, width, rate = map(int, os.getenv(prefix + "_FORMAT", "1 2 16000").split())
        audio.setparams((channels, width, rate, 0, "NONE", ""))
        audio.writeframes(b"\1" * channels * width * 321)
elif name == "gbot":
    (root / "gbot.input").write_text(sys.stdin.read())
    print(text)
elif name == "security":
    account = args[args.index("-a") + 1]
    print(os.getenv(prefix + "_" + account, ""))
