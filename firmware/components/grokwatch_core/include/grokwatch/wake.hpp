#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "grokwatch/audio_level.hpp"
#include "grokwatch/clock.hpp"

namespace grokwatch {

// Cuts speech segments out of the idle microphone stream for server-side wake word checks.
class WakeSegmenter {
public:
    enum class Action { None, Start, Send, Stop };

    static constexpr std::size_t prerollFrames = 15;
    static constexpr unsigned onsetFrames = 3;
    static constexpr unsigned silenceFrames = 25;
    static constexpr unsigned maxFrames = 125;
    static constexpr double onsetRms = 700;
    static constexpr double silenceRms = 500;
    static constexpr Millis resultTimeoutMs = 4000;

    // Start: send wake_start, then the whole preroll (it includes this frame).
    // Send: send this frame. Stop: send this frame, then wake_stop.
    Action frame(const PcmFrame& pcm, double rms, Millis now);
    std::int64_t sequence() const { return sequence_; }
    std::size_t prerollSize() const { return size_; }
    // Index 0 is the oldest frame.
    const PcmFrame& preroll(std::size_t index) const;
    bool awaiting(Millis now) const;
    // Consumes the pending verdict when seq matches the segment being awaited.
    bool result(std::int64_t seq);
    void reset();

private:
    std::array<PcmFrame, prerollFrames> frames_;
    std::size_t head_ = 0;
    std::size_t size_ = 0;
    std::int64_t sequence_ = 0;
    bool active_ = false;
    bool awaiting_ = false;
    unsigned loud_ = 0;
    unsigned quiet_ = 0;
    unsigned total_ = 0;
    Millis deadline_ = 0;
};

}  // namespace grokwatch
