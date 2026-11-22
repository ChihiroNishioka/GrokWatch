from array import array
import math

import pytest

from grokwatch_gateway.resample import Resampler


def tone(count, rate=16000):
    return array("h", [int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(count)]).tobytes()


@pytest.mark.parametrize("source, target", [(16000, 24000), (24000, 16000)])
def test_chunked_equals_one_shot(source, target):
    signal = tone(4000, source)
    whole = Resampler(source, target).process(signal)
    chunked = Resampler(source, target)
    pieces = b"".join(chunked.process(signal[i:i + 641]) for i in range(0, len(signal), 641))
    assert pieces == whole
    assert len(whole) % 2 == 0
    assert abs(len(whole) - len(signal) * target / source) <= 4


def test_ramp_is_monotonic_across_chunks():
    ramp = array("h", range(0, 3000, 3)).tobytes()
    resampler = Resampler(16000, 24000)
    out = array("h")
    for index in range(0, len(ramp), 100):
        out.frombytes(resampler.process(ramp[index:index + 100]))
    assert all(b >= a for a, b in zip(out, out[1:]))
    assert max(b - a for a, b in zip(out, out[1:])) <= 3


def test_odd_byte_lengths_and_empty_input():
    resampler = Resampler(16000, 24000)
    assert resampler.process(b"") == b""
    assert resampler.process(b"\x01") == b""
    assert len(resampler.process(b"\x00" * 1001)) % 2 == 0


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        Resampler(0, 16000)
