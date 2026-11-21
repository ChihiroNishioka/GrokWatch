#include "grokwatch/avatar_scale.hpp"

#include <algorithm>
#include <cmath>

#include "grokwatch/volume.hpp"

namespace grokwatch {
namespace {

double minScale() {
    return std::sqrt(avatarMinArea * faceCenter * faceCenter / (faceRadius * faceRadius));
}

double clampScale(double scale) {
    if (!std::isfinite(scale)) return minScale();
    return std::clamp(scale, minScale(), 1.0);
}

}  // namespace

double avatarScale(std::uint8_t value) {
    const double initialArea = avatarMinArea * faceCenter * faceCenter /
                               (faceRadius * faceRadius);
    const double progress = static_cast<double>(value) / 255.0;
    return std::sqrt(initialArea + (1.0 - initialArea) * progress);
}

DrawnFace scaleFace(const FaceModel& face, double scale) {
    scale = clampScale(scale);
    DrawnFace drawn{};
    drawn.radius = faceRadius * scale;
    drawn.activeDot = face.activeDot;
    for (std::size_t index = 0; index < face.eyes.size(); ++index) {
        const auto& eye = face.eyes[index];
        const double width = std::max(4.0, eye.width * scale);
        const double height = std::max(2.0, eye.height * scale);
        drawn.eyes[index] = {faceCenter + (eye.x - faceCenter) * scale,
                             faceCenter + (eye.y - faceCenter) * scale,
                             width, height, std::min(width, height) / 2.0};
    }

    drawn.ring = {face.ring.kind, face.ring.radius * scale,
                  face.ring.kind == RingKind::None ? 0.0 : std::max(2.0, face.ring.width * scale),
                  face.ring.color, face.ring.segments};
    drawn.dotRadius = std::max(2, static_cast<int>(std::lround(3 * scale)));
    const double spacing = std::max(17 * scale, 2 * drawn.dotRadius + 2.0);
    const double dotY = faceCenter + (face.dots[1].y - faceCenter) * scale;
    drawn.dots = {{{faceCenter - spacing, dotY}, {faceCenter, dotY}, {faceCenter + spacing, dotY}}};
    return drawn;
}

}  // namespace grokwatch
