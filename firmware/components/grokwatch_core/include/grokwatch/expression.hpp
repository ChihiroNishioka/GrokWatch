#pragma once

#include <string_view>

#include "grokwatch/clock.hpp"

namespace grokwatch {

enum class Expression { Neutral, Happy, Sad, Surprised, Thinking };

struct ExpressionShape {
    double width = 1;
    double height = 1;
    double lidInner = 0;
    double lidOuter = 0;
    double lidBottom = 0;
    double gazeY = 0;
};

ExpressionShape shapeOf(Expression expression);
Expression parseExpression(std::string_view text);
ExpressionShape blend(const ExpressionShape& from, const ExpressionShape& to, double fraction);

class ExpressionAnimator {
public:
    // Moves linearly from the current shape to the target, starting after delayMs.
    void set(Expression expression, Millis now, Millis durationMs, Millis delayMs = 0);
    ExpressionShape value(Millis now) const;
    Expression target() const { return target_; }

private:
    Expression target_ = Expression::Neutral;
    ExpressionShape from_{};
    Millis start_ = 0;
    Millis duration_ = 0;
};

}  // namespace grokwatch
