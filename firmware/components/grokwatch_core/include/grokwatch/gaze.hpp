#pragma once

#include "grokwatch/gesture.hpp"

namespace grokwatch {

inline constexpr int screenSize = 466;
inline constexpr int faceCenter = screenSize / 2;
inline constexpr int faceRadius = 200;

struct Vec {
    double x = 0;
    double y = 0;
};

Vec gazeAt(Point point);

class GazeTracker {
public:
    void touch(const GestureEvent& event, Millis now);
    Vec update(Millis now, Vec stateGaze);

private:
    enum class Mode { State, Tap, Drag, Return };
    Mode mode_ = Mode::State;
    Millis updatedAt_ = 0;
    Millis startedAt_ = 0;
    Vec gaze_;
    Vec origin_;
    Vec stateGaze_;
    std::optional<Vec> target_;
};

}  // namespace grokwatch
