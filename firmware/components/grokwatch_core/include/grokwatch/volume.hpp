#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "grokwatch/clock.hpp"

namespace grokwatch {

constexpr int volumeSteps = 51;
constexpr int volumeLevelCount = volumeSteps + 1;
constexpr std::uint8_t volumeStepValue = 5;
constexpr int defaultVolumeLevel = 26;
constexpr std::uint8_t defaultVolumeValue = defaultVolumeLevel * volumeStepValue;
constexpr int speakerMagnification = 8;
constexpr double avatarMinArea = 0.1;
constexpr Millis keyRepeatInitialMs = 400;
constexpr std::array<Millis, 6> keyRepeatIntervalsMs{{200, 160, 130, 100, 80, 60}};
constexpr Millis keyRepeatMinMs = 50;
constexpr unsigned buttonStableSamples = 3;
constexpr int volumeButtonUpGpio = 2;
constexpr int volumeButtonDownGpio = 1;

double speakerGain(int magnification, bool stereo, std::uint8_t master, std::uint8_t channel);

class VolumeControl {
public:
    explicit VolumeControl(int level = defaultVolumeLevel);
    int level() const;
    std::uint8_t value() const;
    void setLevel(int level);
    bool step(int direction);

private:
    int level_;
};

class VolumeKeys {
public:
    int sample(Millis now, bool upPressed, bool downPressed, int level);
    bool takeLogRequest();

private:
    struct Button {
        bool initialized = false;
        bool stable = false;
        bool blocked = false;
        bool candidate = false;
        unsigned samples = 0;
        bool update(bool pressed);
    };

    enum class Mode : std::uint8_t { Waiting, Up, Down, Locked };

    Button up_;
    Button down_;
    Mode mode_ = Mode::Waiting;
    Millis nextRepeatAt_ = 0;
    std::size_t intervalIndex_ = 0;
    bool repeating_ = false;
    bool changed_ = false;
    bool logRequested_ = false;

    void finishPress();
};

}  // namespace grokwatch
