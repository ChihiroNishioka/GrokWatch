#include "gw_test.hpp"
#include "grokwatch/blink.hpp"
using namespace grokwatch;

TEST(idle_and_disconnected_blink_interval) {
    for (auto state : {State::Idle, State::Disconnected})
        for (unsigned seed : {1, 17, 99}) {
            SeededRandom rng(seed);
            Blink blink;
            blink.update(state, 0, rng);
            Millis previous = 0;
            int count = 0;
            for (Millis time = 1; time <= 600000; ++time) {
                if (blink.update(state, time, rng).started) {
                    CHECK(time - previous >= 2000 && time - previous <= 6000);
                    previous = time;
                    ++count;
                }
            }
            CHECK(count >= 100);
        }
}

TEST(no_spontaneous_blink_in_active_states) {
    for (auto state : {State::Listening, State::Thinking, State::Speaking, State::Error}) {
        SeededRandom rng(19);
        Blink blink;
        for (Millis time = 0; time < 7000; ++time)
            CHECK_EQ(blink.update(state, time, rng).scale, 1);
    }
}

TEST(tap_blinks_immediately_150ms) {
    for (auto state : {State::Disconnected, State::Idle, State::Listening,
                       State::Thinking, State::Speaking, State::Error}) {
        SeededRandom rng(19);
        Blink blink;
        blink.trigger(0, rng);
        CHECK(blink.update(state, 0, rng).started);
        CHECK_NEAR(blink.update(state, 60, rng).scale, .08, 1e-6);
        CHECK_NEAR(blink.update(state, 90, rng).scale, .08, 1e-6);
        CHECK_EQ(blink.update(state, 150, rng).scale, 1);
    }
}

TEST(tap_during_blink_does_not_double) {
    struct Steps : Random {
        int calls = 0;
        double unit() override { return calls++ == 0 ? 0 : 1; }
    } rng;
    Blink blink;
    blink.trigger(0, rng);
    CHECK(blink.update(State::Idle, 0, rng).started);
    blink.trigger(70, rng);
    CHECK(!blink.update(State::Idle, 70, rng).started);
    CHECK_EQ(blink.update(State::Idle, 150, rng).scale, 1);
    CHECK(!blink.update(State::Idle, 2000, rng).started);
    CHECK(!blink.update(State::Idle, 6069, rng).started);
    CHECK(blink.update(State::Idle, 6070, rng).started);
}
