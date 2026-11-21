#include "gw_test.hpp"
#include "grokwatch/face_model.hpp"
#include "grokwatch/gesture.hpp"
using namespace grokwatch;

TEST(tap_boundary_300ms) {
    for (int duration : {299, 300}) {
        GestureDetector gesture;
        gesture.update(0, true, Point{0, 0});
        CHECK_EQ(gesture.update(duration, false, {}).kind,
                 duration == 299 ? Gesture::Tap : Gesture::None);
    }
}

TEST(long_press_fires_once_at_600ms_without_tap) {
    GestureDetector gesture;
    gesture.update(0, true, Point{0, 0});
    CHECK_EQ(gesture.update(599, true, Point{12, 0}).kind, Gesture::None);
    CHECK_EQ(gesture.update(600, true, Point{12, 0}).kind, Gesture::LongPress);
    CHECK_EQ(gesture.update(601, true, {}).kind, Gesture::None);
    CHECK_EQ(gesture.update(602, false, {}).kind, Gesture::None);
}

TEST(drag_cancels_long_press) {
    GestureDetector gesture;
    gesture.update(0, true, Point{0, 0});
    CHECK_EQ(gesture.update(50, true, Point{13, 0}).kind, Gesture::DragStart);
    CHECK_EQ(gesture.update(650, true, Point{0, 0}).kind, Gesture::DragMove);
    CHECK_EQ(gesture.update(660, false, {}).kind, Gesture::DragEnd);
}

TEST(swipe_is_reported_as_drag_only) {
    GestureDetector gesture;
    CHECK_EQ(gesture.update(0, true, Point{0, 0}).kind, Gesture::None);
    CHECK_EQ(gesture.update(20, true, Point{80, 0}).kind, Gesture::DragStart);
    CHECK_EQ(gesture.update(50, true, Point{200, 0}).kind, Gesture::DragMove);
    CHECK_EQ(gesture.update(60, false, {}).kind, Gesture::DragEnd);
}

TEST(long_press_cooldown_800ms) {
    for (int offset : {800, 801}) {
        GestureDetector gesture;
        gesture.update(0, true, Point{0, 0});
        CHECK_EQ(gesture.update(600, true, {}).kind, Gesture::LongPress);
        gesture.update(601, false, {});
        gesture.update(offset, true, Point{0, 0});
        CHECK_EQ(gesture.update(600 + offset, true, {}).kind,
                 offset == 800 ? Gesture::None : Gesture::LongPress);
    }
}

TEST(drag_boundary_12px) {
    GestureDetector gesture;
    gesture.update(0, true, Point{0, 0});
    CHECK_EQ(gesture.update(10, true, Point{0, 12}).kind, Gesture::None);
    CHECK_EQ(gesture.update(20, true, Point{1, 12}).kind, Gesture::DragStart);
}

TEST(drag_reports_missing_coordinates_without_reusing_the_last_point) {
    GestureDetector detector;
    detector.sample(0, 1, {1, 1}, {10, 10});
    CHECK_EQ(detector.sample(20, 1, {2, 2}, {30, 30}).kind, Gesture::DragStart);
    for (const auto contacts : {std::optional<unsigned>{}, std::optional<unsigned>{1}}) {
        const auto missing = detector.sample(30, contacts, {0, 0}, {0, 0});
        CHECK_EQ(missing.kind, Gesture::DragMove);
        CHECK(!missing.point);
    }
    const auto resumed = detector.sample(35, 1, {3, 3}, {35, 35});
    CHECK_EQ(resumed.kind, Gesture::DragMove);
    CHECK(resumed.point);
    CHECK_EQ(resumed.point->x, 35);
    CHECK_EQ(detector.sample(40, 0, {0, 0}, {0, 0}).kind, Gesture::DragEnd);
}

TEST(missing_drag_coordinate_holds_the_displayed_gaze) {
    GestureDetector detector;
    FaceAnimator face(1, 0);
    detector.sample(0, 1, {1, 1}, {10, 10});
    const auto start = detector.sample(20, 1, {2, 2}, {433, 233});
    CHECK_EQ(start.kind, Gesture::DragStart);
    face.touch(start, 20);

    const auto visible = face.frame(State::Idle, 100).gaze;
    const auto missing = detector.sample(110, std::nullopt, {0, 0}, {0, 0});
    CHECK_EQ(missing.kind, Gesture::DragMove);
    face.touch(missing, 110);
    const auto held = face.frame(State::Idle, 300).gaze;
    CHECK_NEAR(held.x, visible.x, 1e-6);
    CHECK_NEAR(held.y, visible.y, 1e-6);
    CHECK(!missing.point);
}
