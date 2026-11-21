#include "gw_test.hpp"
#include "grokwatch/avatar_state.hpp"
#include "grokwatch/face_model.hpp"
using namespace grokwatch;

static AvatarStateMachine listening() {
    AvatarStateMachine avatar;
    avatar.hello(0);
    avatar.longPress(0);
    return avatar;
}

static AvatarStateMachine thinking() {
    auto avatar = listening();
    avatar.longPress(1000);
    return avatar;
}

static AvatarStateMachine speaking() {
    auto avatar = thinking();
    avatar.ttsStart(1100);
    return avatar;
}

TEST(boot_is_disconnected_until_hello_ok) {
    AvatarStateMachine avatar;
    CHECK_EQ(avatar.state(), State::Disconnected);
    avatar.hello(0);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(idle_long_press_starts_listening) {
    AvatarStateMachine avatar;
    avatar.hello(0);
    const auto effect = avatar.longPress(0);
    CHECK_EQ(avatar.state(), State::Listening);
    CHECK_EQ(effect.send, Command::ListenStart);
    CHECK(effect.startCapture);
}

TEST(listening_long_press_sends_listen_stop) {
    auto avatar = listening();
    auto effect = avatar.longPress(1000);
    CHECK_EQ(effect.send, Command::ListenStop);
    CHECK(effect.stopCapture);
    CHECK_EQ(makeFace(avatar.state()).ring.kind, RingKind::None);
    avatar.remote(State::Thinking, 1100);
    CHECK_EQ(avatar.state(), State::Thinking);
}

TEST(listening_auto_stop_on_silence_no_speech_and_max) {
    auto avatar = listening();
    avatar.recorded(20, 500);
    for (int frame = 1; frame < 60; ++frame)
        CHECK_EQ(avatar.recorded(20 + frame * 20, 499).send, Command::None);
    CHECK_EQ(avatar.recorded(1220, 499).send, Command::ListenStop);
    CHECK_EQ(avatar.recorded(1240, 499).send, Command::None);
    avatar = listening();
    CHECK_EQ(avatar.tick(4999).send, Command::None);
    CHECK_EQ(avatar.tick(5000).send, Command::ListenStop);
    CHECK_EQ(avatar.tick(5001).send, Command::None);
    avatar = listening();
    for (int frame = 1; frame < 750; ++frame)
        CHECK_EQ(avatar.recorded(frame * 20, 500).send, Command::None);
    CHECK_EQ(avatar.recorded(15000, 500).send, Command::ListenStop);
    CHECK_EQ(avatar.recorded(15020, 500).send, Command::None);
}

TEST(thinking_long_press_cancels) {
    auto avatar = thinking();
    CHECK_EQ(avatar.longPress(2000).send, Command::Cancel);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(speaking_long_press_cancels_and_drops_audio) {
    auto avatar = speaking();
    CHECK(avatar.acceptsPlayback());
    const auto effect = avatar.longPress(2000);
    CHECK_EQ(effect.send, Command::Cancel);
    CHECK(effect.dropPlayback);
    CHECK_EQ(avatar.state(), State::Idle);
    CHECK(!avatar.acceptsPlayback());
}

TEST(full_turn_sequence_defers_idle_until_drained) {
    auto avatar = thinking();
    avatar.remote(State::Speaking, 1100);
    avatar.ttsStart(1101);
    CHECK_EQ(avatar.state(), State::Speaking);
    avatar.remote(State::Idle, 1200);
    CHECK_EQ(avatar.state(), State::Speaking);
    avatar.drained(1300);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(deferred_idle_applies_after_2s) {
    auto avatar = speaking();
    avatar.remote(State::Idle, 1200);
    CHECK(!avatar.tick(3199).dropPlayback);
    CHECK(avatar.tick(3200).dropPlayback);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(error_holds_min_1500ms_then_canned_then_idle) {
    auto avatar = thinking();
    avatar.error(false, true, 1100);
    avatar.remote(State::Speaking, 1200);
    avatar.ttsStart(1201);
    CHECK(avatar.acceptsPlayback());
    avatar.remote(State::Idle, 1300);
    avatar.tick(2599);
    CHECK_EQ(avatar.state(), State::Error);
    CHECK(!avatar.canPlay());
    avatar.tick(2600);
    CHECK_EQ(avatar.state(), State::Speaking);
    CHECK(avatar.canPlay());
    avatar.drained(2650);
    CHECK_EQ(avatar.state(), State::Idle);

    avatar = thinking();
    avatar.error(false, true, 1100);
    avatar.tick(2600);
    CHECK_EQ(avatar.state(), State::Idle);
    avatar.remote(State::Speaking, 2800);
    avatar.ttsStart(2801);
    CHECK(avatar.canPlay());
    CHECK_EQ(avatar.state(), State::Speaking);
}

TEST(no_speech_returns_idle_without_error) {
    auto avatar = thinking();
    CHECK(avatar.error(true, true, 1100).blink);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(thinking_local_timeout_100s) {
    auto avatar = thinking();
    avatar.remote(State::Thinking, 90000);
    CHECK_EQ(avatar.tick(100999).send, Command::None);
    CHECK_EQ(avatar.tick(101000).send, Command::Cancel);
    CHECK_EQ(avatar.state(), State::Error);
    avatar.tick(102500);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(link_down_from_any_state_goes_disconnected) {
    for (auto avatar : {AvatarStateMachine{}, listening(), thinking(), speaking()}) {
        const auto effect = avatar.linkDown(2000);
        CHECK(effect.stopCapture);
        CHECK(effect.dropPlayback);
        CHECK_EQ(avatar.state(), State::Disconnected);
    }
    for (State state : {State::Idle, State::Error}) {
        auto avatar = thinking();
        avatar.remote(state, 1200);
        CHECK_EQ(avatar.state(), state);
        const auto effect = avatar.linkDown(2000);
        CHECK(effect.stopCapture && effect.dropPlayback);
        CHECK_EQ(avatar.state(), State::Disconnected);
    }
}

TEST(long_press_when_disconnected_or_error) {
    AvatarStateMachine avatar;
    auto effect = avatar.longPress(0);
    CHECK_EQ(effect.send, Command::None);
    CHECK(effect.blink);
    CHECK_EQ(avatar.state(), State::Disconnected);
    avatar = thinking();
    avatar.error(false, true, 1100);
    effect = avatar.longPress(1200);
    CHECK_EQ(effect.send, Command::None);
    CHECK(!effect.blink);
    CHECK_EQ(avatar.state(), State::Error);
}

TEST(tap_during_speaking_keeps_state) {
    auto avatar = speaking();
    FaceAnimator face(1, 1100);
    face.frame(avatar.state(), 1100);
    const GestureEvent tap{Gesture::Tap, Point{433, 233}};
    CHECK_EQ(avatar.touch(tap, 1100).send, Command::None);
    face.touch(tap, 1100);
    const auto model = face.frame(avatar.state(), 1220);
    CHECK_NEAR(model.gaze.x, 1.0, 1e-6);
    CHECK(model.blink < 1);
    CHECK_EQ(model.ring.kind, RingKind::Solid);
    CHECK_EQ(avatar.state(), State::Speaking);
}

TEST(drag_during_speaking_keeps_state) {
    auto avatar = speaking();
    FaceAnimator face(1, 1100);
    const GestureEvent start{Gesture::DragStart, Point{433, 233}};
    CHECK_EQ(avatar.touch(start, 1100).send, Command::None);
    face.touch(start, 1100);
    CHECK(face.frame(avatar.state(), 1200).gaze.x > 0.5);
    const GestureEvent move{Gesture::DragMove, Point{420, 233}};
    CHECK_EQ(avatar.touch(move, 1200).send, Command::None);
    face.touch(move, 1200);
    const GestureEvent end{Gesture::DragEnd, {}};
    CHECK_EQ(avatar.touch(end, 1200).send, Command::None);
    face.touch(end, 1200);
    CHECK_NEAR(face.frame(avatar.state(), 1500).gaze.x, 0.0, 1e-6);
    CHECK_EQ(avatar.state(), State::Speaking);
}

TEST(touch_during_disconnected_keeps_ring) {
    FaceAnimator face(1, 0);
    face.frame(State::Disconnected, 0);
    face.touch({Gesture::Tap, Point{433, 233}}, 0);
    const auto tapped = face.frame(State::Disconnected, 120);
    CHECK(tapped.blink < 1 && tapped.gaze.x > 0.9);
    CHECK_EQ(tapped.ring.kind, RingKind::Dashed);
    face.touch({Gesture::DragStart, Point{33, 233}}, 400);
    CHECK(face.frame(State::Disconnected, 510).gaze.x < 0);
    CHECK_EQ(face.frame(State::Disconnected, 510).ring.kind, RingKind::None);
    CHECK_EQ(face.frame(State::Disconnected, 1000).ring.kind, RingKind::Dashed);
}

TEST(delayed_cancel_ack_does_not_stop_new_capture) {
    AvatarStateMachine avatar;
    avatar.hello(0);
    CHECK(avatar.longPress(1).startCapture);
    avatar.longPress(1000);
    CHECK_EQ(avatar.longPress(2000).send, Command::Cancel);
    const auto cancelled = avatar.sessionNumber();
    CHECK(avatar.longPress(3000).startCapture);
    CHECK(avatar.sessionNumber() != cancelled);
    CHECK(!avatar.remote(State::Idle, 3100, cancelled).stopCapture);
    CHECK_EQ(avatar.state(), State::Listening);
    CHECK(avatar.remote(State::Idle, 3110, avatar.sessionNumber()).stopCapture);
}

TEST(delayed_sessionless_state_does_not_stop_new_capture) {
    AvatarStateMachine avatar;
    avatar.hello(0);
    avatar.longPress(1);
    const auto oldSession = avatar.sessionNumber();
    avatar.longPress(1000);
    avatar.remote(State::Idle, 1010, oldSession);
    avatar.longPress(1020);

    CHECK_EQ(avatar.state(), State::Listening);
    CHECK(!avatar.remote(State::Idle, 1030).stopCapture);
    CHECK_EQ(avatar.state(), State::Listening);
}

TEST(delayed_sessionless_error_does_not_stop_new_capture) {
    AvatarStateMachine avatar;
    avatar.hello(0);
    avatar.longPress(1);
    const auto oldSession = avatar.sessionNumber();
    avatar.longPress(1000);
    avatar.remote(State::Idle, 1010, oldSession);
    avatar.longPress(1020);

    CHECK_EQ(avatar.state(), State::Listening);
    avatar.error(true, true, 1030);
    CHECK_EQ(avatar.state(), State::Listening);
}

TEST(delayed_numbered_error_does_not_stop_new_capture) {
    AvatarStateMachine avatar;
    avatar.hello(0);
    avatar.longPress(1);
    const auto oldSession = avatar.sessionNumber();
    avatar.longPress(1000);
    avatar.remote(State::Idle, 1010, oldSession);
    avatar.longPress(1020);

    CHECK_EQ(avatar.state(), State::Listening);
    avatar.error(true, true, 1030, oldSession);
    CHECK_EQ(avatar.state(), State::Listening);
}
