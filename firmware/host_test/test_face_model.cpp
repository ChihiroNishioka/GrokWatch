#include "gw_test.hpp"
#include "grokwatch/face_model.hpp"
#include <algorithm>
#include <utility>
using namespace grokwatch;

TEST(eye_asymmetry_at_right_edge) {
    const auto face = makeFace(State::Idle, {1, 0});
    CHECK_NEAR(face.eyes[0].width, 55, 1e-6);
    CHECK_NEAR(face.eyes[0].height, 81.6, 1e-6);
    CHECK_NEAR(face.eyes[1].width, 33, 1e-6);
    CHECK_NEAR(face.eyes[1].height, 110.4, 1e-6);
}

TEST(eye_asymmetry_mirrors) {
    const auto left = makeFace(State::Idle, {-1, 0});
    const auto right = makeFace(State::Idle, {1, 0});
    const auto center = makeFace(State::Idle);
    for (int i = 0; i < 2; ++i) {
        CHECK_NEAR(left.eyes[i].width, right.eyes[1-i].width, 1e-6);
        CHECK_NEAR(left.eyes[i].height, right.eyes[1-i].height, 1e-6);
        CHECK_EQ(center.eyes[i].width, 44);
        CHECK_EQ(center.eyes[i].height, 96);
    }
}

TEST(eyes_stay_inside_face_all_directions) {
    for (State state : {State::Idle, State::Listening}) {
        for (int degree = -1; degree < 360; ++degree) {
            const auto angle = degree * std::acos(-1.0) / 180;
            const auto model = makeFace(state, degree < 0 ? Vec{} : Vec{std::cos(angle), std::sin(angle)});
            for (const auto& eye : model.eyes)
                for (int x : {-1, 1})
                    for (int y : {-1, 1})
                        CHECK(std::hypot(eye.x - 233 + x * eye.width / 2,
                                         eye.y - 233 + y * eye.height / 2) <= 196);
        }
    }
}

TEST(face_model_ring_per_state) {
    CHECK_EQ(makeFace(State::Idle).ring.kind, RingKind::None);
    const auto listening = makeFace(State::Listening).ring;
    const auto speaking = makeFace(State::Speaking, {}, 1, 0.5).ring;
    const auto error = makeFace(State::Error).ring;
    const auto disconnected = makeFace(State::Disconnected).ring;
    const auto thinking = makeFace(State::Thinking).ring;
    for (auto ring : {listening, speaking, error, disconnected, thinking}) CHECK_EQ(ring.radius, 214);
    CHECK_EQ(listening.kind, RingKind::Solid);
    CHECK_EQ(listening.color, 0x22c7ffu);
    CHECK_EQ(speaking.width, 6);
    CHECK_EQ(error.color, 0xffb000u);
    CHECK_EQ(error.width, 6);
    CHECK_EQ(disconnected.color, 0x808080u);
    CHECK_EQ(disconnected.width, 4);
    CHECK_EQ(disconnected.segments, 12);
    CHECK_EQ(makeFace(State::Disconnected, {}, 1, 0, 499).ring.kind, RingKind::Dashed);
    CHECK_EQ(makeFace(State::Disconnected, {}, 1, 0, 500).ring.kind, RingKind::None);
    CHECK_EQ(makeFace(State::Disconnected, {}, 1, 0, 1000).ring.kind, RingKind::Dashed);
}

TEST(listening_ring_color_width_breath_and_level) {
    const auto at = [](double level, Millis elapsed) {
        return makeFace(State::Listening, {}, 1, level, elapsed).ring;
    };
    CHECK_EQ(at(0, 0).kind, RingKind::Solid);
    CHECK_EQ(at(0, 0).color, 0x22c7ffu);
    CHECK_NEAR(at(0, 0).width, 6, 1e-9);
    CHECK_NEAR(at(0, 300).width, 7.5, 1e-9);
    CHECK_NEAR(at(0, 600).width, 9, 1e-9);
    CHECK_NEAR(at(0, 900).width, 7.5, 1e-9);
    CHECK_NEAR(at(0, 1200).width, 6, 1e-9);
    CHECK_NEAR(at(1, 0).width, 18, 1e-9);
    CHECK_NEAR(at(0.5, 0).width, 12, 1e-9);
    CHECK_NEAR(at(1, 600).width, 21, 1e-9);
    CHECK_NEAR(at(5, 600).width, 21, 1e-9);
    CHECK_NEAR(at(-1, 0).width, 6, 1e-9);
}

TEST(listening_perk_height_curve) {
    const double idle = makeFace(State::Idle).eyes[0].height;
    const struct { Millis elapsed; double factor; } points[] = {
        {0, 1.0}, {60, 1.125}, {120, 1.25}, {210, 1.20}, {300, 1.15}, {1000, 1.15}, {100000, 1.15}};
    for (const auto& point : points)
        CHECK_NEAR(makeFace(State::Listening, {}, 1, 0, point.elapsed).eyes[0].height,
                   idle * point.factor, 1e-9);
    CHECK_NEAR(makeFace(State::Thinking, {}, 1, 0, 120).eyes[0].height, idle, 1e-9);
}

TEST(thinking_arc_spinner) {
    const auto at = [](Millis elapsed) { return makeFace(State::Thinking, {}, 1, 0, elapsed).ring; };
    CHECK_EQ(at(0).kind, RingKind::Arc);
    CHECK_EQ(at(0).color, 0xb07cffu);
    CHECK_EQ(at(0).width, 8);
    CHECK_EQ(at(0).sweep, 100);
    CHECK_EQ(at(0).radius, 214);
    CHECK_NEAR(at(0).start, 0, 1e-9);
    CHECK_NEAR(at(250).start, 90, 1e-9);
    CHECK_NEAR(at(500).start, 180, 1e-9);
    CHECK_NEAR(at(999).start, 359.64, 1e-9);
    CHECK_NEAR(at(1000).start, 0, 1e-9);
    CHECK_NEAR(at(3250).start, 90, 1e-9);
}

TEST(thinking_lids_and_state_lids_only_when_thinking) {
    const auto thinking = makeFace(State::Thinking);
    for (const auto& eye : thinking.eyes) {
        CHECK_EQ(eye.lidInner, 0.22);
        CHECK_EQ(eye.lidOuter, 0.22);
        CHECK_EQ(eye.lidBottom, 0);
    }
    for (State state : {State::Idle, State::Listening, State::Speaking})
        for (const auto& eye : makeFace(state).eyes)
            CHECK_EQ(eye.lidInner + eye.lidOuter + eye.lidBottom, 0);
    // The larger of the state lid and the expression lid wins.
    const auto sad = makeFace(State::Thinking, {}, 1, 0, 0, shapeOf(Expression::Sad));
    CHECK_EQ(sad.eyes[0].lidInner, 0.22);
    CHECK_EQ(sad.eyes[0].lidOuter, 0.40);
    const auto fullLid = ExpressionShape{1, 1, 0.5, 0.1, 0.3, 0};
    const auto mixed = makeFace(State::Thinking, {}, 1, 0, 0, fullLid);
    CHECK_EQ(mixed.eyes[1].lidInner, 0.5);
    CHECK_EQ(mixed.eyes[1].lidOuter, 0.22);
    CHECK_EQ(mixed.eyes[1].lidBottom, 0.3);
}

TEST(thinking_gaze_sways_and_looks_up) {
    FaceAnimator face(1, 0);
    face.frame(State::Thinking, 0);
    CHECK_NEAR(face.frame(State::Thinking, 600).gaze.x, 0.4, 1e-6);
    CHECK_NEAR(face.frame(State::Thinking, 600).gaze.y, -0.3, 1e-6);
    CHECK_NEAR(face.frame(State::Thinking, 1800).gaze.x, -0.4, 1e-6);
    CHECK_NEAR(face.frame(State::Thinking, 2400).gaze.x, 0, 1e-6);
    CHECK_NEAR(thinkingGaze(600).x, 0.4, 1e-9);
    CHECK_NEAR(thinkingGaze(1234).y, -0.3, 1e-9);
}

TEST(thinking_long_wait_hint) {
    FaceAnimator face(1, 0);
    face.frame(State::Thinking, 0);
    CHECK_EQ(face.frame(State::Thinking, 19900).activeDot, -1);
    for (int i = 0; i < 4; ++i) {
        const auto model = face.frame(State::Thinking, 20000 + i * 200);
        CHECK_EQ(model.activeDot, i % 3);
        for (auto dot : model.dots) CHECK(dot.y > 433);
    }
}

TEST(expression_shape_applies_to_eyes) {
    const auto base = makeFace(State::Idle);
    const auto surprised = makeFace(State::Idle, {}, 1, 0, 0, shapeOf(Expression::Surprised));
    CHECK_NEAR(surprised.eyes[0].width, 44 * 1.2, 1e-9);
    CHECK_NEAR(surprised.eyes[0].height, 96 * 1.2, 1e-9);
    CHECK_NEAR(surprised.eyes[0].y, 233 + 50 * -0.05, 1e-9);
    const auto happy = makeFace(State::Idle, {}, 1, 0, 0, shapeOf(Expression::Happy));
    CHECK_EQ(happy.eyes[0].lidBottom, 0.55);
    CHECK_NEAR(happy.eyes[0].y, 233 - 5, 1e-9);
    const auto sad = makeFace(State::Idle, {}, 1, 0, 0, shapeOf(Expression::Sad));
    CHECK_NEAR(sad.eyes[1].height, 96 * 0.9, 1e-9);
    CHECK_EQ(sad.eyes[1].lidOuter, 0.4);
    CHECK_EQ(base.eyes[0].lidOuter, 0);
    for (const auto& eye : surprised.eyes) CHECK_NEAR(eye.radius, std::min(eye.width, eye.height) / 2, 1e-9);
}

TEST(fit_inside_keeps_every_corner_within_196) {
    const double pi = std::acos(-1.0);
    for (const auto& setup : {std::pair{State::Idle, Expression::Surprised},
                              std::pair{State::Listening, Expression::Neutral},
                              std::pair{State::Listening, Expression::Surprised}}) {
        for (Millis elapsed : {Millis{0}, Millis{60}, Millis{120}, Millis{210}, Millis{300}}) {
            for (int degree = -1; degree < 360; ++degree) {
                for (double length : {0.5, 1.0}) {
                    const auto angle = degree * pi / 180;
                    const Vec gaze = degree < 0 ? Vec{} : Vec{length * std::cos(angle), length * std::sin(angle)};
                    const auto model = makeFace(setup.first, gaze, 1, 0, elapsed, shapeOf(setup.second));
                    for (const auto& eye : model.eyes) {
                        CHECK(eye.width > 0 && eye.height > 0);
                        for (int x : {-1, 1})
                            for (int y : {-1, 1})
                                CHECK(std::hypot(eye.x - 233 + x * eye.width / 2,
                                                 eye.y - 233 + y * eye.height / 2) <= 196 + 1e-9);
                    }
                }
            }
        }
    }
}

TEST(fit_inside_shrinks_oversized_eyes_by_one_ratio) {
    const ExpressionShape huge{2, 2, 0, 0, 0, 0};
    bool shrunk = false;
    for (int degree = 0; degree < 360; degree += 5) {
        const auto angle = degree * std::acos(-1.0) / 180;
        const Vec gaze{std::cos(angle), std::sin(angle)};
        const auto model = makeFace(State::Listening, gaze, 1, 0, 120, huge);
        for (int i = 0; i < 2; ++i) {
            const double direction = (i == 0 ? -1 : 1) * gaze.x;
            const double width = 44 * (1 - 0.25 * direction) * 2;
            const double height = 96 * (1 + 0.15 * direction) * 1.25 * 2;
            const auto& eye = model.eyes[i];
            CHECK_NEAR(eye.width / eye.height, width / height, 1e-9);
            CHECK(eye.width <= width + 1e-9 && eye.height <= height + 1e-9);
            CHECK_NEAR(eye.radius, std::min(eye.width, eye.height) / 2, 1e-9);
            for (int x : {-1, 1})
                for (int y : {-1, 1})
                    CHECK(std::hypot(eye.x - 233 + x * eye.width / 2,
                                     eye.y - 233 + y * eye.height / 2) <= 196 + 1e-9);
            shrunk |= eye.height < height - 1;
        }
    }
    CHECK(shrunk);
    // Eyes that already fit are left alone.
    const auto fits = makeFace(State::Listening, {}, 1, 0, 120, shapeOf(Expression::Surprised));
    CHECK_NEAR(fits.eyes[0].height, 96 * 1.25 * 1.2, 1e-9);
    CHECK_NEAR(fits.eyes[0].width, 44 * 1.2, 1e-9);
}
