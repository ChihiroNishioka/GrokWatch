from array import array
import sys


class Resampler:
    """Streaming linear-interpolation resampler for PCM16 little-endian mono.

    The phase and the last unconsumed samples are kept across calls, so feeding a
    signal in arbitrary chunks gives the same output as feeding it in one piece.
    """

    def __init__(self, source_rate, target_rate):
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("Sample rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._buffer = array("h")
        self._phase = 0  # Position of the next output in the buffer, in 1/target_rate source samples.
        self._odd = b""

    def process(self, pcm):
        data = self._odd + bytes(pcm)
        usable = len(data) & ~1
        self._odd = data[usable:]
        if not usable:
            return b""
        incoming = array("h")
        incoming.frombytes(data[:usable])
        if sys.byteorder == "big":
            incoming.byteswap()
        buffer = self._buffer
        buffer.extend(incoming)
        out = array("h")
        step, unit = self.source_rate, self.target_rate
        phase, last = self._phase, len(buffer) - 1
        while (index := phase // unit) < last:
            a = buffer[index]
            out.append(a + ((buffer[index + 1] - a) * (phase - index * unit)) // unit)
            phase += step
        keep = min(phase // unit, len(buffer))
        self._buffer = buffer[keep:]
        self._phase = phase - keep * unit
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()
