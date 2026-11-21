#include "gw_test.hpp"
#include "grokwatch/face_model.hpp"
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
    for (State state : {State::Idle, State::Thinking})
        CHECK_EQ(makeFace(state).ring.kind, RingKind::None);
    const auto listening = makeFace(State::Listening).ring;
    const auto speaking = makeFace(State::Speaking, {}, 1, 0.5).ring;
    const auto error = makeFace(State::Error).ring;
    const auto disconnected = makeFace(State::Disconnected).ring;
    for (auto ring : {listening, speaking, error, disconnected}) CHECK_EQ(ring.radius, 214);
    CHECK_EQ(listening.color, 0xffffffu);
    CHECK_EQ(listening.width, 4);
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

TEST(listening_eyes_taller) {
    CHECK_NEAR(makeFace(State::Listening).eyes[0].height,
               makeFace(State::Idle).eyes[0].height * 1.15, 1e-6);
}

TEST(thinking_sway_and_long_wait_hint) {
    FaceAnimator face(1, 0);
    face.frame(State::Thinking, 0);
    CHECK_NEAR(face.frame(State::Thinking, 600).gaze.x, 0.5, 1e-6);
    CHECK_NEAR(face.frame(State::Thinking, 1800).gaze.x, -0.5, 1e-6);
    CHECK_NEAR(face.frame(State::Thinking, 2400).gaze.x, 0, 1e-6);
    CHECK_EQ(face.frame(State::Thinking, 19900).activeDot, -1);
    for (int i = 0; i < 4; ++i) {
        const auto model = face.frame(State::Thinking, 20000 + i * 200);
        CHECK_EQ(model.activeDot, i % 3);
        for (auto dot : model.dots) CHECK(dot.y > 433);
    }
}
