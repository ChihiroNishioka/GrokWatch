#include "gw_test.hpp"
#include "grokwatch/wake.hpp"
using namespace grokwatch;
using Action = WakeSegmenter::Action;

namespace {
PcmFrame tagged(int tag) {
    PcmFrame frame{};
    frame[0] = static_cast<std::int16_t>(tag);
    return frame;
}

// Frames arrive every 20 ms; the tag records the frame number.
struct Feed {
    WakeSegmenter segmenter;
    int index = 0;
    Millis now = 0;
    Action push(double rms) {
        const auto action = segmenter.frame(tagged(index++), rms, now);
        now += 20;
        return action;
    }
};
}

TEST(wake_onset_needs_three_loud_frames) {
    Feed feed;
    CHECK_EQ(feed.push(700), Action::None);
    CHECK_EQ(feed.push(700), Action::None);
    CHECK_EQ(feed.push(699), Action::None);
    CHECK_EQ(feed.push(700), Action::None);
    CHECK_EQ(feed.push(700), Action::None);
    CHECK_EQ(feed.push(5000), Action::Start);
    CHECK_EQ(feed.segmenter.sequence(), 1);
    CHECK_EQ(feed.push(5000), Action::Send);
}

TEST(wake_preroll_is_oldest_first_and_includes_current_frame) {
    Feed feed;
    for (int i = 0; i < 5; ++i) feed.push(100);
    feed.push(1000);
    feed.push(1000);
    CHECK_EQ(feed.push(1000), Action::Start);
    CHECK_EQ(feed.segmenter.prerollSize(), 8u);
    for (std::size_t i = 0; i < 8; ++i) CHECK_EQ(feed.segmenter.preroll(i)[0], static_cast<int>(i));

    Feed full;
    for (int i = 0; i < 40; ++i) full.push(100);
    full.push(1000);
    full.push(1000);
    CHECK_EQ(full.push(1000), Action::Start);
    CHECK_EQ(full.segmenter.prerollSize(), 15u);
    for (std::size_t i = 0; i < 15; ++i)
        CHECK_EQ(full.segmenter.preroll(i)[0], static_cast<int>(28 + i));
    CHECK_EQ(full.segmenter.preroll(14)[0], 42);
}

TEST(wake_silence_stops_after_25_quiet_frames) {
    Feed feed;
    for (int i = 0; i < 3; ++i) feed.push(1000);
    for (int i = 0; i < 24; ++i) CHECK_EQ(feed.push(499), Action::Send);
    // A frame in the hysteresis band resets the silence count.
    CHECK_EQ(feed.push(500), Action::Send);
    for (int i = 0; i < 24; ++i) CHECK_EQ(feed.push(100), Action::Send);
    CHECK_EQ(feed.push(100), Action::Stop);
    CHECK(feed.segmenter.awaiting(feed.now));
}

TEST(wake_segment_is_capped_at_125_frames_including_preroll) {
    Feed feed;
    for (int i = 0; i < 20; ++i) feed.push(100);
    for (int i = 0; i < 2; ++i) feed.push(3000);
    CHECK_EQ(feed.push(3000), Action::Start);
    int total = 15;
    Action action = Action::Send;
    while (action == Action::Send) {
        action = feed.push(3000);
        ++total;
    }
    CHECK_EQ(action, Action::Stop);
    CHECK_EQ(total, 125);

    Feed small;
    for (int i = 0; i < 3; ++i) small.push(3000);
    CHECK_EQ(small.segmenter.prerollSize(), 3u);
    int frames = 3;
    do { action = small.push(3000); ++frames; } while (action == Action::Send);
    CHECK_EQ(frames, 125);
}

TEST(wake_awaiting_blocks_new_segments_until_result_or_timeout) {
    Feed feed;
    for (int i = 0; i < 3; ++i) feed.push(1000);
    Action action = Action::Send;
    while (action == Action::Send) action = feed.push(100);
    CHECK_EQ(action, Action::Stop);
    const Millis stopped = feed.now - 20;
    CHECK(feed.segmenter.awaiting(stopped));
    CHECK(feed.segmenter.awaiting(stopped + 3999));
    CHECK(!feed.segmenter.awaiting(stopped + 4000));
    for (int i = 0; i < 10; ++i) CHECK_EQ(feed.push(5000), Action::None);
    // Preroll keeps updating while waiting.
    CHECK_EQ(feed.segmenter.prerollSize(), 15u);
    CHECK_EQ(feed.segmenter.preroll(14)[0], feed.index - 1);

    CHECK(!feed.segmenter.result(2));
    CHECK(!feed.segmenter.result(0));
    CHECK(feed.segmenter.result(1));
    CHECK(!feed.segmenter.result(1));
    CHECK(!feed.segmenter.awaiting(feed.now));
    // Loud audio must be heard afresh for three frames after the wait.
    CHECK_EQ(feed.push(5000), Action::None);
    CHECK_EQ(feed.push(5000), Action::None);
    CHECK_EQ(feed.push(5000), Action::Start);
    CHECK_EQ(feed.segmenter.sequence(), 2);
}

TEST(wake_timeout_releases_segmenter) {
    Feed feed;
    for (int i = 0; i < 3; ++i) feed.push(1000);
    Action action = Action::Send;
    while (action == Action::Send) action = feed.push(100);
    const Millis stopped = feed.now - 20;
    feed.now = stopped + 3999;
    CHECK_EQ(feed.push(5000), Action::None);
    feed.now = stopped + 4000;
    CHECK_EQ(feed.push(5000), Action::None);
    CHECK(!feed.segmenter.result(1));
    CHECK_EQ(feed.push(5000), Action::None);
    CHECK_EQ(feed.push(5000), Action::Start);
    CHECK_EQ(feed.segmenter.sequence(), 2);
}

TEST(wake_reset_discards_segment_and_wait) {
    Feed feed;
    for (int i = 0; i < 3; ++i) feed.push(1000);
    feed.push(1000);
    feed.segmenter.reset();
    CHECK_EQ(feed.segmenter.prerollSize(), 0u);
    CHECK_EQ(feed.push(100), Action::None);
    CHECK_EQ(feed.segmenter.prerollSize(), 1u);
    CHECK(!feed.segmenter.result(1));

    Feed waiting;
    for (int i = 0; i < 3; ++i) waiting.push(1000);
    Action action = Action::Send;
    while (action == Action::Send) action = waiting.push(100);
    waiting.segmenter.reset();
    CHECK(!waiting.segmenter.awaiting(waiting.now));
    CHECK(!waiting.segmenter.result(1));
    // A reset segment never continues: the next loud run starts a new one with a new seq.
    CHECK_EQ(waiting.push(2000), Action::None);
    CHECK_EQ(waiting.push(2000), Action::None);
    CHECK_EQ(waiting.push(2000), Action::Start);
    CHECK_EQ(waiting.segmenter.sequence(), 2);
    CHECK_EQ(waiting.segmenter.prerollSize(), 3u);
}
