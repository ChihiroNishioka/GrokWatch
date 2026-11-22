#include "grokwatch/drift.hpp"

#include <cmath>

namespace grokwatch {

namespace {

constexpr double twoPi = 6.283185307179586;
constexpr double driftRadius = 0.35;

Vec pickTarget(Vec previous, Random& rng) {
    const double angle = twoPi * rng.unit();
    const double radius = driftRadius * std::sqrt(rng.unit());
    const Vec candidate{radius * std::cos(angle), radius * std::sin(angle)};
    if (std::hypot(candidate.x - previous.x, candidate.y - previous.y) >= 0.1) {
        return candidate;
    }

    // Keep adjacent targets far enough apart for movement to be visible in any five-second window.
    const double distance = std::hypot(previous.x, previous.y);
    if (distance == 0) return {driftRadius, 0};
    return {-driftRadius * previous.x / distance, -driftRadius * previous.y / distance};
}

}  // namespace

DriftSample Drift::update(Millis now, Random& rng) {
    if (!started_) end_ = now;
    bool newTarget = false;
    while (now >= end_) {
        started_ = true;
        start_ = end_;
        end_ += 1500 + static_cast<Millis>(2500 * rng.unit());
        origin_ = target_;
        target_ = pickTarget(origin_, rng);
        newTarget = true;
    }
    const double progress = double(now - start_) / (end_ - start_);
    const double eased = progress * progress * (3 - 2 * progress);
    return {{origin_.x + (target_.x - origin_.x) * eased,
             origin_.y + (target_.y - origin_.y) * eased}, target_, newTarget};
}

Vec thinkingGaze(Millis elapsed) {
    return {0.4 * std::sin(twoPi * (elapsed % 2400) / 2400), -0.3};
}

}  // namespace grokwatch
