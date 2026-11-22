#pragma once

#include <array>
#include <cstdint>

#include "grokwatch/face_model.hpp"

namespace grokwatch {

struct DrawnPoint {
    double x;
    double y;
};

struct DrawnRing {
    RingKind kind;
    double radius;
    double width;
    std::uint32_t color;
    int segments;
    double start;
    double sweep;
};

struct DrawnFace {
    double radius;
    std::array<Eye, 2> eyes;
    DrawnRing ring;
    std::array<DrawnPoint, 3> dots;
    int dotRadius;
    int activeDot;
};

double avatarScale(std::uint8_t value);
DrawnFace scaleFace(const FaceModel& face, double scale);

}  // namespace grokwatch
