#include "grokwatch/gaze.hpp"

#include <algorithm>
#include <cmath>

namespace grokwatch {

namespace {

Vec mix(Vec from, Vec to, double fraction) {
    return {from.x + (to.x - from.x) * fraction, from.y + (to.y - from.y) * fraction};
}

}  // namespace

Vec gazeAt(Point point) {
    const double x = double(point.x) - faceCenter;
    const double y = double(point.y) - faceCenter;
    const double denominator = std::max(double(faceRadius), std::hypot(x, y));
    return {x / denominator, y / denominator};
}

void GazeTracker::touch(const GestureEvent& event, Millis now) {
    switch (event.kind) {
        case Gesture::Tap:
            if (event.point) {
                origin_ = update(now, stateGaze_);
                target_ = gazeAt(*event.point);
                startedAt_ = now;
                mode_ = Mode::Tap;
            }
            break;
        case Gesture::DragStart:
        case Gesture::DragMove:
            // A missing sample freezes the displayed gaze until tracking resumes.
            if (event.point) {
                update(now, stateGaze_);
                target_ = gazeAt(*event.point);
            } else {
                target_.reset();
                updatedAt_ = now;
            }
            mode_ = Mode::Drag;
            break;
        case Gesture::DragEnd:
            origin_ = update(now, stateGaze_);
            startedAt_ = now;
            mode_ = Mode::Return;
            break;
        case Gesture::None:
        case Gesture::LongPress:
            break;
    }
}

Vec GazeTracker::update(Millis now, Vec stateGaze) {
    stateGaze_ = stateGaze;
    if (mode_ == Mode::Tap) {
        const auto elapsed = now - startedAt_;
        if (elapsed < 1620) {
            gaze_ = mix(origin_, *target_, std::clamp(elapsed / 120.0, 0.0, 1.0));
        } else {
            origin_ = *target_;
            startedAt_ += 1620;
            mode_ = Mode::Return;
        }
    }

    if (mode_ == Mode::Drag && target_) {
        const auto elapsed = std::max<Millis>(0, now - updatedAt_);
        gaze_ = mix(gaze_, *target_, 1 - std::exp(-elapsed / 80.0));
    }
    if (mode_ == Mode::Return) {
        const auto elapsed = now - startedAt_;
        if (elapsed >= 300) {
            mode_ = Mode::State;
        } else {
            gaze_ = mix(origin_, stateGaze, std::max(0.0, elapsed / 300.0));
        }
    }
    if (mode_ == Mode::State) gaze_ = stateGaze;

    updatedAt_ = now;
    return gaze_;
}

}  // namespace grokwatch
