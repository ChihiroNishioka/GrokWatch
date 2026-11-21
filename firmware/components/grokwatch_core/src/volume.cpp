#include "grokwatch/volume.hpp"

#include <algorithm>

namespace grokwatch {
namespace {

int boundedLevel(int level) {
    return std::clamp(level, 0, volumeSteps);
}

int stepLevel(int level, int direction) {
    if (direction == 1) return std::min(level + 1, volumeSteps);
    if (direction == -1) return std::max(level - 1, 0);
    return level;
}

}  // namespace

double speakerGain(int magnification, bool stereo, std::uint8_t master, std::uint8_t channel) {
    const double outputChannels = stereo ? 2.0 : 1.0;
    const double volume = master;
    const double channelVolume = channel;
    return (magnification * outputChannels * volume * volume * channelVolume * channelVolume) /
           68719476736.0;
}

VolumeControl::VolumeControl(int level) : level_(boundedLevel(level)) {}

int VolumeControl::level() const {
    return level_;
}

std::uint8_t VolumeControl::value() const {
    return static_cast<std::uint8_t>(level_ * volumeStepValue);
}

void VolumeControl::setLevel(int level) {
    level_ = boundedLevel(level);
}

bool VolumeControl::step(int direction) {
    const int next = stepLevel(level_, direction);
    const bool changed = next != level_;
    level_ = next;
    return changed;
}

bool VolumeKeys::Button::update(bool pressed) {
    if (!initialized) {
        initialized = true;
        stable = pressed;
        candidate = pressed;
        blocked = pressed;
        return false;
    }
    if (pressed == stable) {
        candidate = pressed;
        samples = 0;
        return false;
    }
    if (pressed != candidate) {
        candidate = pressed;
        samples = 1;
    } else if (samples < buttonStableSamples) {
        ++samples;
    }
    if (samples < buttonStableSamples) return false;

    stable = candidate;
    samples = 0;
    if (blocked) {
        if (!stable) blocked = false;
        return false;
    }
    return true;
}

int VolumeKeys::sample(Millis now, bool upPressed, bool downPressed, int level) {
    const bool upChanged = up_.update(upPressed);
    const bool downChanged = down_.update(downPressed);
    level = boundedLevel(level);

    if (mode_ == Mode::Locked) {
        if (!up_.stable && !down_.stable) mode_ = Mode::Waiting;
        return level;
    }

    if (mode_ == Mode::Waiting) {
        if (up_.stable && down_.stable) {
            mode_ = Mode::Locked;
        } else if (upChanged && up_.stable) {
            mode_ = Mode::Up;
            intervalIndex_ = 0;
            nextRepeatAt_ = now + keyRepeatInitialMs;
            const int next = stepLevel(level, 1);
            changed_ = next != level;
            repeating_ = changed_;
            level = next;
        } else if (downChanged && down_.stable) {
            mode_ = Mode::Down;
            intervalIndex_ = 0;
            nextRepeatAt_ = now + keyRepeatInitialMs;
            const int next = stepLevel(level, -1);
            changed_ = next != level;
            repeating_ = changed_;
            level = next;
        }
        return level;
    }

    if (up_.stable && down_.stable) {
        finishPress();
        mode_ = Mode::Locked;
        repeating_ = false;
        return level;
    }

    if (repeating_ && now >= nextRepeatAt_) {
        const int next = stepLevel(level, mode_ == Mode::Up ? 1 : -1);
        if (next == level) {
            repeating_ = false;
        } else {
            level = next;
            changed_ = true;
            const auto interval = intervalIndex_ < keyRepeatIntervalsMs.size()
                                      ? keyRepeatIntervalsMs[intervalIndex_]
                                      : keyRepeatMinMs;
            intervalIndex_ = std::min(intervalIndex_ + 1, keyRepeatIntervalsMs.size());
            nextRepeatAt_ = now + interval;
            if (level == 0 || level == volumeSteps) repeating_ = false;
        }
    }

    const bool keyHeld = mode_ == Mode::Up ? up_.stable : down_.stable;
    if (!keyHeld) {
        finishPress();
        mode_ = Mode::Waiting;
        repeating_ = false;
    }
    return level;
}

bool VolumeKeys::takeLogRequest() {
    const bool requested = logRequested_;
    logRequested_ = false;
    return requested;
}

void VolumeKeys::finishPress() {
    if (changed_) logRequested_ = true;
    changed_ = false;
}

}  // namespace grokwatch
