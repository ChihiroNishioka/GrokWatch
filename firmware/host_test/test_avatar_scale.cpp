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
                    for (Millis elapsed : {Millis{0}, Millis{499}, Millis{500}, Millis{20000},
                                           Millis{20200}, Millis{20400}}) {
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
                        for (std::size_t i = 0; i < face.dots.size(); ++i) {
                            CHECK_EQ(drawn.dots[i].x, face.dots[i].x);
                            CHECK_EQ(drawn.dots[i].y, face.dots[i].y);
                        }
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
    const Millis elapsedValues[] = {0, 499, 500, 20000, 20200, 20400};
    for (int value : values) {
        for (State state : {State::Idle, State::Listening, State::Thinking, State::Speaking,
                            State::Error, State::Disconnected}) {
            for (int degree = 0; degree < 360; ++degree) {
                const double angle = degree * std::acos(-1.0) / 180;
                for (double length : lengths) {
                    for (double blink : {1.0, 0.08}) {
                        for (double speaking : {0.0, 0.5, 1.0}) {
                            for (Millis elapsed : elapsedValues) {
                                const auto face = makeFace(state,
                                    {length * std::cos(angle), length * std::sin(angle)},
                                    blink, speaking, elapsed);
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
}

TEST(scaled_face_table) {
    struct Dimensions {
        int value;
        double faceRadius;
        double eyeCenterOffset;
        double maxGaze;
        double eyeWidth;
        double openEyeHeight;
        double blinkEyeHeight;
        double ringRadius;
        double listeningWidth;
        double speakingMinWidth;
        double speakingMaxWidth;
        double errorWidth;
        double dotOffset;
        double dotSpacing;
        int dotRadius;
    };
    const Dimensions table[] = {
        {0, 73.7, 25.8, 18.4, 16.2, 35.4, 2.4, 78.8, 2.00, 2.00, 3.68, 2.21, 78.8, 6.26, 2},
        {65, 119.3, 41.8, 29.8, 26.3, 57.3, 3.9, 127.7, 2.39, 2.00, 5.97, 3.58, 127.7, 10.1, 2},
        {130, 151.8, 53.1, 38.0, 33.4, 72.9, 4.95, 162.5, 3.04, 2.00, 7.59, 4.56, 162.5, 12.9, 2},
        {195, 178.5, 62.5, 44.6, 39.3, 85.7, 5.8, 191.0, 3.57, 2.00, 8.93, 5.36, 191.0, 15.2, 3},
        {255, 200.0, 70.0, 50.0, 44.0, 96.0, 6.5, 214.0, 4.00, 2.00, 10.0, 6.00, 214.0, 17.0, 3},
    };
    const Millis elapsedValues[] = {0, 499, 500, 20000, 20200, 20400};
    for (const auto& expected : table) {
        const double scale = avatarScale(static_cast<std::uint8_t>(expected.value));
        for (Millis elapsed : elapsedValues) {
            const auto idle = scaleFace(makeFace(State::Idle, {}, 1, 0, elapsed), scale);
            CHECK_NEAR(idle.radius, expected.faceRadius, 0.05);
            CHECK_NEAR(faceCenter - idle.eyes[0].x, expected.eyeCenterOffset, 0.05);
            CHECK_NEAR(idle.eyes[0].width, expected.eyeWidth, 0.05);
            CHECK_NEAR(idle.eyes[0].height, expected.openEyeHeight, 0.05);
            CHECK_NEAR(idle.dots[1].y - faceCenter, expected.dotOffset, 0.05);
            CHECK_NEAR(idle.dots[1].x - idle.dots[0].x, expected.dotSpacing, 0.05);
            CHECK_EQ(idle.dotRadius, expected.dotRadius);

            const auto gaze = scaleFace(makeFace(State::Idle, {1, 0}, 1, 0, elapsed), scale);
            CHECK_NEAR(gaze.eyes[0].x - idle.eyes[0].x, expected.maxGaze, 0.05);
            const auto blink = scaleFace(makeFace(State::Idle, {1, 0}, 0.08, 0, elapsed), scale);
            CHECK_NEAR(blink.eyes[0].height, expected.blinkEyeHeight, 0.05);

            const auto listening = scaleFace(makeFace(State::Listening, {}, 1, 0, elapsed), scale);
            CHECK_NEAR(listening.ring.radius, expected.ringRadius, 0.05);
            CHECK_NEAR(listening.ring.width, expected.listeningWidth, 0.05);
            const auto speakingMin = scaleFace(makeFace(State::Speaking, {}, 1, 0, elapsed), scale);
            const auto speakingMax = scaleFace(makeFace(State::Speaking, {}, 1, 1, elapsed), scale);
            CHECK_NEAR(speakingMin.ring.width, expected.speakingMinWidth, 0.05);
            CHECK_NEAR(speakingMax.ring.width, expected.speakingMaxWidth, 0.05);
            const auto error = scaleFace(makeFace(State::Error, {}, 1, 0, elapsed), scale);
            CHECK_NEAR(error.ring.width, expected.errorWidth, 0.05);
        }
    }
}

TEST(scaled_face_minimums) {
    const int values[] = {0, 5, 65, 125, 130, 195, 250, 255};
    const Vec gazes[] = {{}, {1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    const Millis elapsedValues[] = {0, 499, 500, 20000, 20200, 20400};
    for (int value : values) {
        for (State state : {State::Idle, State::Listening, State::Thinking, State::Speaking,
                            State::Error, State::Disconnected}) {
            for (Vec gaze : gazes) {
                for (double blink : {1.0, 0.08}) {
                    for (double level : {0.0, 1.0}) {
                        for (Millis elapsed : elapsedValues) {
                            const auto drawn = scaleFace(makeFace(state, gaze, blink, level, elapsed),
                                avatarScale(static_cast<std::uint8_t>(value)));
                            for (const auto& eye : drawn.eyes) {
                                CHECK(eye.width >= 4);
                                CHECK(eye.height >= 2);
                                CHECK(eye.radius <= std::min(eye.width, eye.height) / 2);
                            }
                            if (drawn.ring.kind != RingKind::None) CHECK(drawn.ring.width >= 2);
                            CHECK(drawn.dotRadius >= 2);
                        }
                    }
                }
            }
        }
    }
}

TEST(scale_changes_during_speaking_and_thinking) {
    for (State state : {State::Speaking, State::Thinking}) {
        FaceAnimator actual(31, 0);
        int value = 0;
        int direction = 5;
        for (Millis now = 0; now <= 20400; now += 33) {
            const double level = static_cast<double>((now / 33) % 101) / 100;
            const auto drawn = scaleFace(actual.frame(state, now, level),
                avatarScale(static_cast<std::uint8_t>(value)));
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
            value += direction;
            if (value == 255) direction = -5;
            if (value == 0) direction = 5;
        }
    }
}
