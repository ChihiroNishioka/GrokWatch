#include "gw_test.hpp"
#include "grokwatch/gaze.hpp"
#include <initializer_list>
using namespace grokwatch;

TEST(gaze_center_is_zero) {
    const auto gaze = gazeAt({233, 233});
    CHECK_EQ(gaze.x, 0);
    CHECK_EQ(gaze.y, 0);
}

TEST(gaze_clamps_corners_and_offscreen) {
    for (auto point : {Point{0,0}, Point{465,0}, Point{0,465}, Point{465,465},
                       Point{-50,600}, Point{10000,-10000}}) {
        const auto gaze = gazeAt(point);
        const auto dx = point.x - 233.0;
        const auto dy = point.y - 233.0;
        CHECK_NEAR(std::hypot(gaze.x, gaze.y), 1.0, 1e-6);
        CHECK_NEAR(gaze.x, dx / std::hypot(dx, dy), 1e-6);
        CHECK_NEAR(gaze.y, dy / std::hypot(dx, dy), 1e-6);
    }
}

TEST(gaze_inside_circle_unclamped) {
    const auto gaze = gazeAt({273, 133});
    CHECK_NEAR(gaze.x, 0.2, 1e-6);
    CHECK_NEAR(gaze.y, -0.5, 1e-6);
}

TEST(drag_smoothing_time_constant) {
    GazeTracker gaze;
    gaze.touch({Gesture::DragStart, Point{433, 233}}, 0);
    CHECK_NEAR(gaze.update(33, {}).x, 1 - std::exp(-33.0 / 80), 0.02);
}

TEST(release_returns_in_300ms) {
    GazeTracker gaze;
    gaze.touch({Gesture::DragStart, Point{433, 233}}, 0);
    double previous = gaze.update(300, {}).x;
    gaze.touch({Gesture::DragEnd, {}}, 300);
    for (int time = 310; time <= 600; time += 10) {
        const auto x = gaze.update(time, {}).x;
        CHECK(x >= 0 && x <= previous);
        previous = x;
    }
    CHECK_NEAR(previous, 0, 1e-6);
}

TEST(tap_gaze_timing_and_missing_point) {
    GazeTracker gaze;
    gaze.touch({Gesture::Tap, Point{433, 233}}, 0);
    CHECK(gaze.update(119, {}).x < 1);
    CHECK_NEAR(gaze.update(120, {}).x, 1, 1e-6);
    CHECK_NEAR(gaze.update(1620, {}).x, 1, 1e-6);
    CHECK_NEAR(gaze.update(1920, {}).x, 0, 1e-6);
    gaze.touch({Gesture::DragStart, Point{433, 233}}, 2000);
    const auto before = gaze.update(2033, {}).x;
    gaze.touch({Gesture::DragMove, {}}, 2033);
    CHECK_NEAR(gaze.update(2066, {}).x, before, 1e-6);
}
