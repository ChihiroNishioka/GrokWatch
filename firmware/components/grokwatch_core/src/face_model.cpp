#include "grokwatch/face_model.hpp"

#include <algorithm>
#include <cmath>

namespace grokwatch {

namespace {

constexpr double twoPi = 6.283185307179586;
constexpr double eyeLimit = 196;

// Height multiplier for the ears-up motion right after entering Listening.
double listenPerk(Millis elapsed) {
    if (elapsed <= 0) return 1;
    if (elapsed < 120) return 1 + 0.25 * elapsed / 120;
    if (elapsed < 300) return 1.25 - 0.10 * (elapsed - 120) / 180;
    return 1.15;
}

// Shrinks width and height by one ratio so every corner of the bounding box stays inside.
void fitInside(Eye& eye) {
    const double dx = std::abs(eye.x - faceCenter);
    const double dy = std::abs(eye.y - faceCenter);
    const double hw = eye.width / 2;
    const double hh = eye.height / 2;
    if (std::hypot(dx + hw, dy + hh) <= eyeLimit) return;
    const double a = hw * hw + hh * hh;
    const double b = dx * hw + dy * hh;
    const double c = dx * dx + dy * dy - eyeLimit * eyeLimit;
    const double ratio = c >= 0 ? 0.0 : (-b + std::sqrt(b * b - a * c)) / a;
    eye.width *= ratio;
    eye.height *= ratio;
}

}  // namespace

FaceModel makeFace(State state, Vec gaze, double blink, double level, Millis elapsed,
                   const ExpressionShape& shape) {
    FaceModel model{};
    model.gaze = gaze;
    model.blink = blink;
    const double perk = state == State::Listening ? listenPerk(elapsed) : 1;
    const double lidFloor = state == State::Thinking ? 0.22 : 0;
    for (std::size_t index = 0; index < model.eyes.size(); ++index) {
        const int side = index == 0 ? -1 : 1;
        const double direction = side * gaze.x;
        const double width = 44 * (1 - 0.25 * direction) * shape.width;
        const double height = 96 * (1 + 0.15 * direction) * perk * shape.height * blink;
        auto& eye = model.eyes[index];
        eye = {faceCenter + 70 * side + 50 * gaze.x,
               faceCenter + 50 * (gaze.y + shape.gazeY), width, height,
               0, std::max(lidFloor, shape.lidInner), std::max(lidFloor, shape.lidOuter),
               shape.lidBottom};
        fitInside(eye);
        eye.radius = std::min(eye.width, eye.height) / 2;
    }

    switch (state) {
        case State::Listening: {
            const double breath = 0.5 - 0.5 * std::cos(twoPi * (elapsed % 1200) / 1200.0);
            model.ring = {RingKind::Solid, 214,
                          6 + 3 * breath + 12 * std::clamp(level, 0.0, 1.0), 0x22c7ff, 0};
            break;
        }
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
            model.ring = {RingKind::Arc, 214, 8, 0xb07cff, 0, 360.0 * (elapsed % 1000) / 1000.0, 100};
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
        if (state_) {
            enteredAt_ = now;
            if (state == State::Listening || state == State::Thinking ||
                state == State::Disconnected) {
                expression_.set(Expression::Neutral, now, 150);
            } else if (*state_ == State::Speaking) {
                expression_.set(Expression::Neutral, now, 300, 1200);
            }
        }
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
                    level, elapsed, expression_.value(now));
}

void FaceAnimator::touch(const GestureEvent& event, Millis now) {
    gaze_.touch(event, now);
    if (event.kind == Gesture::Tap) triggerBlink(now);
}

void FaceAnimator::setExpression(Expression expression, Millis now) {
    expression_.set(expression, now, 200);
}

void FaceAnimator::triggerBlink(Millis now) {
    blink_.trigger(now, blinkRng_);
}

}  // namespace grokwatch
