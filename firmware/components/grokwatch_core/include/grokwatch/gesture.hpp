#pragma once

#include <optional>

#include "grokwatch/clock.hpp"

namespace grokwatch {

struct Point {
    int x;
    int y;
};

enum class Gesture { None, Tap, LongPress, DragStart, DragMove, DragEnd };

struct GestureEvent {
    Gesture kind = Gesture::None;
    std::optional<Point> point;
};

class GestureDetector {
public:
    GestureEvent update(Millis now, bool pressed, std::optional<Point> point);

private:
    enum class Contact { Up, Pressed, Held, Dragging };
    Contact contact_ = Contact::Up;
    Millis pressedAt_ = 0;
    std::optional<Millis> lastLongPress_;
    std::optional<Point> origin_;
    std::optional<Point> lastPoint_;
};

}  // namespace grokwatch
