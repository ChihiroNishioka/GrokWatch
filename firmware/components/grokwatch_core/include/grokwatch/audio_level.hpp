#pragma once
#include "grokwatch/clock.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace grokwatch {

constexpr int sampleRate = 16000;
constexpr std::size_t samplesPerFrame = 320;
constexpr std::size_t bytesPerFrame = samplesPerFrame * 2;
using PcmFrame = std::array<std::int16_t, samplesPerFrame>;

double rms(const PcmFrame& data);
double rawLevel(double rms);

class AudioLevel {
public:
    void frame(Millis now, double rms);
    double value(Millis now) const;

private:
    std::optional<Millis> lastFrame_;
    double level_ = 0;
};

class Vad {
public:
    bool frame(double rms);
    bool heardSpeech() const { return heard_; }

private:
    bool heard_ = false;
    unsigned silentFrames_ = 0;
};

class PlaybackBuffer {
public:
    void clear();
    void start();
    bool push(const PcmFrame& frame);
    bool pop(PcmFrame& frame);
    void end();
    bool complete() const;
    std::size_t droppedFrames() const { return dropped_; }

private:
    // Covers the initial burst plus the Error hold before playback begins.
    std::array<PcmFrame, 96> frames_;
    std::size_t read_ = 0;
    std::size_t size_ = 0;
    std::size_t dropped_ = 0;
    bool active_ = false;
    bool started_ = false;
    bool ended_ = false;
};

}
