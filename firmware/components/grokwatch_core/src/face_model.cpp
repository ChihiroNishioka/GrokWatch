#include "grokwatch/face_model.hpp"

#include <algorithm>

namespace grokwatch {

FaceModel makeFace(State state, Vec gaze, double blink, double level, Millis elapsed) {
    FaceModel model{};
    model.gaze = gaze;
    model.blink = blink;
    for (std::size_t index = 0; index < model.eyes.size(); ++index) {
        const int side = index == 0 ? -1 : 1;
        const double direction = side * gaze.x;
        const double width = 44 * (1 - 0.25 * direction);
        const double height = 96 * (1 + 0.15 * direction) *
                              (state == State::Listening ? 1.15 : 1) * blink;
        model.eyes[index] = {faceCenter + 70 * side + 50 * gaze.x,
                             faceCenter + 50 * gaze.y, width, height,
                             std::min(width, height) / 2};
    }

    switch (state) {
        case State::Listening:
            model.ring = {RingKind::Solid, 214, 4, 0xffffff, 0};
            break;
        case State::Speaking:
            model.ring = {RingKind::Solid, 214, 2 + 8 * std::clamp(level, 0.0, 1.0), 0xffffff, 0};
            break;
        case State::Error:
            model.ring = {RingKind::Solid, 214, 6, 0xffb000, 0};
            break;
        case State::Disconnected:
            if (elapsed % 1000 < 500) {
                model.ring = {RingKind::Dashed, 214, 4, 0x808080, 12};
            }
            break;
        case State::Thinking:
            if (elapsed >= 20000) model.activeDot = int((elapsed - 20000) / 200 % 3);
            break;
        case State::Idle:
            break;
    }
    return model;
}

FaceAnimator::FaceAnimator(std::uint32_t seed, Millis start)
    : enteredAt_(start), blinkRng_(seed), driftRng_(seed ^ 0x9e3779b9u) {}

FaceModel FaceAnimator::frame(State state, Millis now, double level) {
    if (!state_ || state != *state_) {
        if (state_) enteredAt_ = now;
        state_ = state;
    }
    const auto elapsed = now - enteredAt_;
    Vec stateGaze;
    if (state == State::Idle || state == State::Disconnected) {
        stateGaze = drift_.update(now, driftRng_).gaze;
    } else if (state == State::Thinking) {
        stateGaze = thinkingGaze(elapsed);
    }
    return makeFace(state, gaze_.update(now, stateGaze), blink_.update(state, now, blinkRng_).scale,
                    level, elapsed);
}

void FaceAnimator::touch(const GestureEvent& event, Millis now) {
    gaze_.touch(event, now);
    if (event.kind == Gesture::Tap) triggerBlink(now);
}

void FaceAnimator::triggerBlink(Millis now) {
    blink_.trigger(now, blinkRng_);
}

}  // namespace grokwatch
