#include "grokwatch/audio_level.hpp"
#include <algorithm>
#include <cmath>

namespace grokwatch {

double rms(const PcmFrame& data) {
    double sum = 0;
    for (const double sample : data) sum += sample * sample;
    return std::sqrt(sum / data.size());
}

double rawLevel(double amplitude) {
    return std::clamp(amplitude / 6000, 0.0, 1.0);
}

void AudioLevel::frame(Millis now, double amplitude) {
    const auto target = rawLevel(amplitude);
    const auto previous = value(now);
    const auto constant = target > previous ? 30.0 : 120.0;
    level_ = previous + (target - previous) * (1 - std::exp(-20 / constant));
    lastFrame_ = now;
}

double AudioLevel::value(Millis now) const {
    if (!lastFrame_) return 0;
    const auto decay = std::max<Millis>(0, now - *lastFrame_ - 100);
    return level_ * std::max(0.0, 1 - decay / 200.0);
}

bool Vad::frame(double amplitude) {
    if (amplitude >= 500) {
        heard_ = true;
        silentFrames_ = 0;
    } else if (heard_) {
        ++silentFrames_;
    }
    return silentFrames_ >= 60;
}

void PlaybackBuffer::clear() {
    read_ = size_ = 0;
    active_ = started_ = ended_ = false;
}

void PlaybackBuffer::start() {
    clear();
    dropped_ = 0;
    active_ = true;
}

bool PlaybackBuffer::push(const PcmFrame& frame) {
    if (!active_ || ended_) return false;
    if (size_ == frames_.size()) {
        read_ = (read_ + 1) % frames_.size();
        --size_;
        ++dropped_;
    }
    frames_[(read_ + size_) % frames_.size()] = frame;
    ++size_;
    return true;
}

bool PlaybackBuffer::pop(PcmFrame& frame) {
    if (!size_ || (!started_ && !ended_ && size_ < 15)) return false;
    started_ = true;
    frame = frames_[read_];
    read_ = (read_ + 1) % frames_.size();
    --size_;
    return true;
}

void PlaybackBuffer::end() {
    if (active_) ended_ = true;
}

bool PlaybackBuffer::complete() const {
    return active_ && ended_ && size_ == 0;
}

}
