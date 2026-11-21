#include "grokwatch/gesture.hpp"

namespace grokwatch {

GestureEvent GestureDetector::update(Millis now, bool pressed, std::optional<Point> point) {
    if (!pressed) {
        const auto previous = contact_;
        contact_ = Contact::Up;
        if (previous == Contact::Dragging) return {Gesture::DragEnd, {}};
        if (previous == Contact::Pressed && now - pressedAt_ < 300) {
            return {Gesture::Tap, lastPoint_};
        }
        return {};
    }

    if (contact_ == Contact::Up) {
        contact_ = Contact::Pressed;
        pressedAt_ = now;
        origin_ = lastPoint_ = point;
        return {};
    }

    if (point) {
        lastPoint_ = point;
        if (!origin_) origin_ = point;
    }
    if (contact_ == Contact::Dragging) return {Gesture::DragMove, point};

    if (point) {
        const auto dx = double(point->x) - origin_->x;
        const auto dy = double(point->y) - origin_->y;
        if (dx * dx + dy * dy > 12 * 12) {
            contact_ = Contact::Dragging;
            return {Gesture::DragStart, point};
        }
    }

    if (contact_ == Contact::Pressed && now - pressedAt_ >= 600) {
        contact_ = Contact::Held;
        if (!lastLongPress_ || now - *lastLongPress_ > 800) {
            lastLongPress_ = now;
            return {Gesture::LongPress, lastPoint_};
        }
    }
    return {};
}

}  // namespace grokwatch
