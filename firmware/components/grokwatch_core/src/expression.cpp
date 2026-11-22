#include "grokwatch/expression.hpp"

#include <algorithm>

namespace grokwatch {

ExpressionShape shapeOf(Expression expression) {
    switch (expression) {
        case Expression::Neutral: return {1, 1, 0, 0, 0, 0};
        case Expression::Happy: return {1.05, 1, 0, 0, 0.55, -0.10};
        case Expression::Sad: return {1, 0.9, 0, 0.40, 0, 0.25};
        case Expression::Surprised: return {1.2, 1.2, 0, 0, 0, -0.05};
        case Expression::Thinking: return {1, 1, 0.22, 0.22, 0, -0.30};
    }
    return {};
}

Expression parseExpression(std::string_view text) {
    if (text == "happy") return Expression::Happy;
    if (text == "sad") return Expression::Sad;
    if (text == "surprised") return Expression::Surprised;
    if (text == "thinking") return Expression::Thinking;
    return Expression::Neutral;
}

ExpressionShape blend(const ExpressionShape& from, const ExpressionShape& to, double fraction) {
    const auto mix = [fraction](double a, double b) { return a + (b - a) * fraction; };
    return {mix(from.width, to.width), mix(from.height, to.height),
            mix(from.lidInner, to.lidInner), mix(from.lidOuter, to.lidOuter),
            mix(from.lidBottom, to.lidBottom), mix(from.gazeY, to.gazeY)};
}

void ExpressionAnimator::set(Expression expression, Millis now, Millis durationMs,
                             Millis delayMs) {
    from_ = value(now);
    target_ = expression;
    start_ = now + std::max<Millis>(0, delayMs);
    duration_ = std::max<Millis>(0, durationMs);
}

ExpressionShape ExpressionAnimator::value(Millis now) const {
    const auto to = shapeOf(target_);
    if (now <= start_) return duration_ == 0 && now == start_ ? to : from_;
    if (duration_ == 0 || now - start_ >= duration_) return to;
    return blend(from_, to, double(now - start_) / duration_);
}

}  // namespace grokwatch
