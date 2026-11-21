#include "gw_test.hpp"
#include "grokwatch/avatar_scale.hpp"
#include "grokwatch/volume.hpp"

#include <algorithm>
#include <cmath>

using namespace grokwatch;

TEST(scale_formula_values) {
    CHECK_NEAR(avatarScale(0), 0.36841, 0.0001);
    CHECK_NEAR(avatarScale(130), 0.75917, 0.0001);
    CHECK_EQ(avatarScale(255), 1.0);
    CHECK_NEAR(200 * avatarScale(0), 73.7, 0.05);
    CHECK_NEAR(200 * avatarScale(130), 151.8, 0.05);
    CHECK_NEAR(200 * avatarScale(255), 200.0, 0.05);
    CHECK_NEAR(std::pow(200 * avatarScale(0) / (screenSize / 2), 2), 0.1, 0.001);
}

TEST(scale_area_linear) {
    double previousArea = 0;
    double previousDelta = -1;
    for (int value = 0; value <= 255; ++value) {
        const double radius = faceRadius * avatarScale(static_cast<std::uint8_t>(value));
        const double area = radius * radius;
        if (value > 0) {
            const double delta = area - previousArea;
            CHECK(delta > 0);
            if (previousDelta >= 0) CHECK_NEAR(delta, previousDelta, 1e-9);
            previousDelta = delta;
        }
        previousArea = area;
    }
}

TEST(scale_one_is_identity) {
    for (State state : {State::Idle, State::Listening, State::Thinking, State::Speaking,
                        State::Error, State::Disconnected}) {
        for (const Vec gaze : {Vec{}, Vec{1, 0}, Vec{0, -1}, Vec{0.5, -0.5}}) {
            for (double blink : {1.0, 0.08}) {
                for (double level : {0.0, 0.5, 1.0}) {
                    for (Millis elapsed : {Millis{0}, Millis{500}, Millis{20000}, Millis{20400}}) {
                        const auto face = makeFace(state, gaze, blink, level, elapsed);
                        const auto drawn = scaleFace(face, 1.0);
                        CHECK_EQ(drawn.radius, faceRadius);
                        CHECK_EQ(drawn.eyes.size(), face.eyes.size());
                        for (std::size_t i = 0; i < face.eyes.size(); ++i) {
                            CHECK_EQ(drawn.eyes[i].x, face.eyes[i].x);
                            CHECK_EQ(drawn.eyes[i].y, face.eyes[i].y);
                            CHECK_EQ(drawn.eyes[i].width, face.eyes[i].width);
                            CHECK_EQ(drawn.eyes[i].height, face.eyes[i].height);
                            CHECK_EQ(drawn.eyes[i].radius, face.eyes[i].radius);
                        }
                        CHECK_EQ(drawn.ring.radius, face.ring.radius);
                        CHECK_EQ(drawn.ring.width, face.ring.width);
                        CHECK_EQ(drawn.dots[0].x, face.dots[0].x);
                        CHECK_EQ(drawn.dots[0].y, face.dots[0].y);
                        CHECK_EQ(drawn.dotRadius, 3);
                        CHECK_EQ(drawn.activeDot, face.activeDot);
                    }
                }
            }
        }
    }
}

TEST(scaled_face_stays_inside_all_states) {
    const int values[] = {0, 5, 65, 125, 130, 195, 250, 255};
    const double lengths[] = {0, 0.5, 1};
    for (int value : values) {
        for (State state : {State::Idle, State::Listening, State::Thinking, State::Speaking,
                            State::Error, State::Disconnected}) {
            for (int degree = 0; degree < 360; ++degree) {
                const double angle = degree * std::acos(-1.0) / 180;
                for (double length : lengths) {
                    for (double blink : {1.0, 0.08}) {
                        for (double speaking : {0.0, 0.5, 1.0}) {
                            const auto face = makeFace(state,
                                {length * std::cos(angle), length * std::sin(angle)},
                                blink, speaking, 20400);
                            const auto drawn = scaleFace(face, avatarScale(static_cast<std::uint8_t>(value)));
                            const int faceLimit = std::lround(drawn.radius);
                            for (const auto& eye : drawn.eyes) {
                                CHECK(eye.width >= 4);
                                CHECK(eye.height >= 2);
                                CHECK(eye.radius <= std::min(eye.width, eye.height) / 2);
                                const int x = std::lround(eye.x - eye.width / 2);
                                const int y = std::lround(eye.y - eye.height / 2);
                                const int width = std::lround(eye.width);
                                const int height = std::lround(eye.height);
                                for (int px : {x, x + width}) for (int py : {y, y + height}) {
                                    CHECK(std::hypot(px - faceCenter, py - faceCenter) <=
                                          196 * avatarScale(static_cast<std::uint8_t>(value)) + 1e-6);
                                    CHECK(std::hypot(px - faceCenter, py - faceCenter) <= faceLimit);
                                }
                            }
                            if (drawn.ring.kind != RingKind::None) {
                                CHECK(std::lround(drawn.ring.width) >= 2);
                                const int outer = std::lround(drawn.ring.radius + drawn.ring.width / 2);
                                const int inner = outer - std::lround(drawn.ring.width);
                                CHECK(inner > faceLimit + 1);
                                CHECK(outer <= 232);
                            }
                            CHECK(drawn.dotRadius >= 2);
                            for (int i = 0; i < 2; ++i) {
                                CHECK(drawn.dots[i + 1].x - drawn.dots[i].x >= 2 * drawn.dotRadius + 2);
                            }
                            for (const auto& dot : drawn.dots) {
                                CHECK(std::hypot(dot.x - faceCenter, dot.y - faceCenter) - drawn.dotRadius > faceLimit);
                                CHECK(dot.x - drawn.dotRadius >= 0 && dot.x + drawn.dotRadius < screenSize);
                                CHECK(dot.y - drawn.dotRadius >= 0 && dot.y + drawn.dotRadius < screenSize);
                            }
                        }
                    }
                }
            }
        }
    }
}

TEST(scaled_face_table) {
    const int values[] = {0, 65, 130, 195, 255};
    const double expectedRadius[] = {73.7, 119.3, 151.8, 178.5, 200.0};
    for (std::size_t i = 0; i < std::size(values); ++i) {
        const auto drawn = scaleFace(makeFace(State::Idle), avatarScale(static_cast<std::uint8_t>(values[i])));
        CHECK_NEAR(drawn.radius, expectedRadius[i], 0.05);
    }
}

TEST(scale_changes_during_speaking_and_thinking) {
    FaceAnimator actual(31, 0);
    FaceAnimator baseline(31, 0);
    for (State state : {State::Speaking, State::Thinking}) {
        for (Millis now = 0; now <= 20400; now += 33) {
            const double level = static_cast<double>((now / 33) % 101) / 100;
            const auto original = actual.frame(state, now, level);
            const auto same = baseline.frame(state, now, level);
            const auto drawn = scaleFace(original, avatarScale(static_cast<std::uint8_t>((now / 33 * 5) % 256)));
            CHECK_EQ(original.gaze.x, same.gaze.x);
            CHECK_EQ(original.gaze.y, same.gaze.y);
            CHECK_EQ(original.blink, same.blink);
            CHECK_EQ(original.activeDot, same.activeDot);
            CHECK(drawn.radius >= faceRadius * avatarScale(0));
            CHECK(drawn.radius <= faceRadius);
        }
    }
}
