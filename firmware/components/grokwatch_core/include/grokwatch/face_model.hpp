#pragma once

#include <array>
#include <cstdint>
#include <optional>

#include "grokwatch/blink.hpp"
#include "grokwatch/drift.hpp"

namespace grokwatch {

struct Eye {
    double x;
    double y;
    double width;
    double height;
    double radius;
};

enum class RingKind { None, Solid, Dashed };

struct Ring {
    RingKind kind = RingKind::None;
    int radius = 214;
    double width = 0;
    std::uint32_t color = 0;
    int segments = 0;
};

struct FaceModel {
    Vec gaze;
    double blink;
    std::array<Eye, 2> eyes;
    Ring ring;
    std::array<Point, 3> dots{{{216, 447}, {233, 447}, {250, 447}}};
    int activeDot = -1;
};

FaceModel makeFace(State state, Vec gaze = {}, double blink = 1, double level = 0,
                   Millis elapsed = 0);

class FaceAnimator {
public:
    FaceAnimator(std::uint32_t seed, Millis start);
    FaceModel frame(State state, Millis now, double level = 0);
    void touch(const GestureEvent& event, Millis now);
    void triggerBlink(Millis now);

private:
    Millis enteredAt_;
    std::optional<State> state_;
    SeededRandom blinkRng_;
    SeededRandom driftRng_;
    GazeTracker gaze_;
    Drift drift_;
    Blink blink_;
};

}  // namespace grokwatch
