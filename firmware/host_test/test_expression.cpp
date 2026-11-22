#include "gw_test.hpp"
#include "grokwatch/expression.hpp"
#include "grokwatch/face_model.hpp"
using namespace grokwatch;

TEST(expression_table_values) {
    struct Row { Expression expression; double w, h, inner, outer, bottom, gazeY; };
    const Row rows[] = {
        {Expression::Neutral, 1, 1, 0, 0, 0, 0},
        {Expression::Happy, 1.05, 1, 0, 0, 0.55, -0.10},
        {Expression::Sad, 1, 0.9, 0, 0.40, 0, 0.25},
        {Expression::Surprised, 1.2, 1.2, 0, 0, 0, -0.05},
        {Expression::Thinking, 1, 1, 0.22, 0.22, 0, -0.30},
    };
    for (const auto& row : rows) {
        const auto shape = shapeOf(row.expression);
        CHECK_EQ(shape.width, row.w);
        CHECK_EQ(shape.height, row.h);
        CHECK_EQ(shape.lidInner, row.inner);
        CHECK_EQ(shape.lidOuter, row.outer);
        CHECK_EQ(shape.lidBottom, row.bottom);
        CHECK_EQ(shape.gazeY, row.gazeY);
    }
}

TEST(parse_expression_known_and_unknown) {
    CHECK_EQ(parseExpression("neutral"), Expression::Neutral);
    CHECK_EQ(parseExpression("happy"), Expression::Happy);
    CHECK_EQ(parseExpression("sad"), Expression::Sad);
    CHECK_EQ(parseExpression("surprised"), Expression::Surprised);
    CHECK_EQ(parseExpression("thinking"), Expression::Thinking);
    for (std::string_view text : {"", "angry", "HAPPY", "happy ", "Sad"})
        CHECK_EQ(parseExpression(text), Expression::Neutral);
}

TEST(expression_blend_is_linear) {
    const auto mid = blend(shapeOf(Expression::Neutral), shapeOf(Expression::Happy), 0.5);
    CHECK_NEAR(mid.width, 1.025, 1e-12);
    CHECK_NEAR(mid.lidBottom, 0.275, 1e-12);
    CHECK_NEAR(mid.gazeY, -0.05, 1e-12);
    CHECK_EQ(blend(shapeOf(Expression::Sad), shapeOf(Expression::Happy), 0).lidOuter, 0.40);
    CHECK_EQ(blend(shapeOf(Expression::Sad), shapeOf(Expression::Happy), 1).lidOuter, 0);
}

TEST(expression_animator_200ms_transition) {
    ExpressionAnimator animator;
    CHECK_EQ(animator.value(0).height, 1);
    animator.set(Expression::Surprised, 1000, 200);
    CHECK_EQ(animator.target(), Expression::Surprised);
    CHECK_EQ(animator.value(1000).width, 1);
    CHECK_NEAR(animator.value(1100).width, 1.1, 1e-12);
    CHECK_NEAR(animator.value(1200).width, 1.2, 1e-12);
    CHECK_NEAR(animator.value(5000).width, 1.2, 1e-12);
    // Retargeting starts from the shape shown at that moment.
    animator.set(Expression::Neutral, 1300, 100);
    CHECK_NEAR(animator.value(1300).width, 1.2, 1e-12);
    animator.set(Expression::Sad, 2000, 200);
    animator.set(Expression::Neutral, 2100, 200);
    CHECK_NEAR(animator.value(2100).lidOuter, 0.2, 1e-12);
    CHECK_NEAR(animator.value(2200).lidOuter, 0.1, 1e-12);
}

TEST(expression_animator_delay_holds_current_shape) {
    ExpressionAnimator animator;
    animator.set(Expression::Happy, 0, 200);
    animator.set(Expression::Neutral, 1000, 300, 1200);
    CHECK_NEAR(animator.value(1000).lidBottom, 0.55, 1e-12);
    CHECK_NEAR(animator.value(2199).lidBottom, 0.55, 1e-12);
    CHECK_NEAR(animator.value(2350).lidBottom, 0.275, 1e-12);
    CHECK_NEAR(animator.value(2500).lidBottom, 0, 1e-12);
    animator.set(Expression::Sad, 3000, 0);
    CHECK_EQ(animator.value(3000).lidOuter, 0.4);
}

TEST(face_animator_set_expression_takes_200ms) {
    FaceAnimator face(1, 0);
    face.frame(State::Thinking, 0);
    face.frame(State::Speaking, 100);
    face.setExpression(Expression::Surprised, 1000);
    CHECK_NEAR(face.frame(State::Speaking, 1000).eyes[0].width, 44, 1e-9);
    CHECK_NEAR(face.frame(State::Speaking, 1100).eyes[0].width, 44 * 1.1, 1e-9);
    CHECK_NEAR(face.frame(State::Speaking, 1200).eyes[0].width, 44 * 1.2, 1e-9);
}

TEST(face_animator_speaking_exit_holds_1200_then_fades_300) {
    for (State next : {State::Idle, State::Error}) {
        FaceAnimator face(1, 0);
        face.frame(State::Speaking, 0);
        face.setExpression(Expression::Happy, 0);
        CHECK_NEAR(face.frame(State::Speaking, 500).eyes[0].lidBottom, 0.55, 1e-9);
        face.frame(next, 1000);
        CHECK_NEAR(face.frame(next, 1000).eyes[0].lidBottom, 0.55, 1e-9);
        CHECK_NEAR(face.frame(next, 2199).eyes[0].lidBottom, 0.55, 1e-9);
        CHECK_NEAR(face.frame(next, 2350).eyes[0].lidBottom, 0.275, 1e-9);
        CHECK_NEAR(face.frame(next, 2500).eyes[0].lidBottom, 0, 1e-9);
    }
}

TEST(face_animator_entering_listening_thinking_disconnected_resets_in_150ms) {
    for (State next : {State::Listening, State::Thinking, State::Disconnected}) {
        FaceAnimator face(1, 0);
        face.frame(State::Speaking, 0);
        face.setExpression(Expression::Happy, 0);
        face.frame(State::Speaking, 300);
        face.frame(next, 1000);
        CHECK_NEAR(face.frame(next, 1075).eyes[0].lidBottom, 0.275, 1e-9);
        CHECK_NEAR(face.frame(next, 1150).eyes[0].lidBottom, 0, 1e-9);
    }
    FaceAnimator idle(1, 0);
    idle.frame(State::Idle, 0);
    idle.setExpression(Expression::Happy, 0);
    idle.frame(State::Idle, 300);
    CHECK_EQ(idle.frame(State::Idle, 5000).eyes[0].lidBottom, 0.55);
    idle.frame(State::Listening, 5000);
    CHECK_NEAR(idle.frame(State::Listening, 5150).eyes[0].lidBottom, 0, 1e-9);
}

TEST(face_animator_expression_does_not_reset_when_entering_speaking) {
    FaceAnimator face(1, 0);
    face.frame(State::Thinking, 0);
    face.setExpression(Expression::Sad, 1000);
    face.frame(State::Speaking, 1100);
    CHECK_NEAR(face.frame(State::Speaking, 1300).eyes[0].lidOuter, 0.4, 1e-9);
    CHECK_NEAR(face.frame(State::Speaking, 5000).eyes[0].lidOuter, 0.4, 1e-9);
}
