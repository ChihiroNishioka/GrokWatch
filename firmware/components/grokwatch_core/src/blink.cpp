#include "grokwatch/blink.hpp"

namespace grokwatch {

namespace {

Millis interval(Random& rng) {
    return 2000 + static_cast<Millis>(4000 * rng.unit());
}

}  // namespace

void Blink::trigger(Millis now, Random& rng) {
    if (!startedAt_ || now - *startedAt_ >= 150) {
        startedAt_ = now;
        reportStart_ = true;
    }
    dueAt_ = now + interval(rng);
}

BlinkSample Blink::update(State state, Millis now, Random& rng) {
    const bool automatic = state == State::Idle || state == State::Disconnected;
    if (automatic) {
        if (!dueAt_) dueAt_ = now + interval(rng);
        if (now >= *dueAt_) trigger(now, rng);
    } else if (wasAutomatic_) {
        dueAt_.reset();
    }
    wasAutomatic_ = automatic;

    BlinkSample sample{1, reportStart_};
    reportStart_ = false;
    if (!startedAt_) return sample;

    const auto elapsed = now - *startedAt_;
    constexpr double closed = 0.08;
    if (elapsed < 60) {
        sample.scale = 1 - (1 - closed) * elapsed / 60;
    } else if (elapsed <= 90) {
        sample.scale = closed;
    } else if (elapsed < 150) {
        sample.scale = closed + (1 - closed) * (elapsed - 90) / 60;
    } else {
        startedAt_.reset();
    }
    return sample;
}

}  // namespace grokwatch
