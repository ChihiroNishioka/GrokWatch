#include "grokwatch/wake.hpp"

namespace grokwatch {

const PcmFrame& WakeSegmenter::preroll(std::size_t index) const {
    return frames_[(head_ + index) % frames_.size()];
}

WakeSegmenter::Action WakeSegmenter::frame(const PcmFrame& pcm, double rms, Millis now) {
    if (size_ == frames_.size()) {
        frames_[head_] = pcm;
        head_ = (head_ + 1) % frames_.size();
    } else {
        frames_[(head_ + size_) % frames_.size()] = pcm;
        ++size_;
    }

    if (awaiting_ && now >= deadline_) awaiting_ = false;
    if (active_) {
        ++total_;
        quiet_ = rms < silenceRms ? quiet_ + 1 : 0;
        if (quiet_ >= silenceFrames || total_ >= maxFrames) {
            active_ = false;
            awaiting_ = true;
            deadline_ = now + resultTimeoutMs;
            loud_ = 0;
            return Action::Stop;
        }
        return Action::Send;
    }
    if (awaiting_) return Action::None;

    loud_ = rms >= onsetRms ? loud_ + 1 : 0;
    if (loud_ < onsetFrames) return Action::None;
    loud_ = 0;
    quiet_ = 0;
    total_ = static_cast<unsigned>(size_);
    active_ = true;
    ++sequence_;
    return Action::Start;
}

bool WakeSegmenter::awaiting(Millis now) const {
    return awaiting_ && now < deadline_;
}

bool WakeSegmenter::result(std::int64_t seq) {
    if (!awaiting_ || seq != sequence_) return false;
    awaiting_ = false;
    return true;
}

void WakeSegmenter::reset() {
    head_ = size_ = 0;
    active_ = awaiting_ = false;
    loud_ = quiet_ = total_ = 0;
}

}  // namespace grokwatch
