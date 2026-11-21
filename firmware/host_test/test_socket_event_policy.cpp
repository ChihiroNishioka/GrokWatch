#include "gw_test.hpp"
#include "grokwatch/socket_event_policy.hpp"
using namespace grokwatch;

TEST(audio_overflow_is_counted_without_hiding_control_order) {
    SocketEventPolicy policy;
    std::uint32_t dropped = 0;
    for (int frame = 0; frame < 32; ++frame)
        CHECK_EQ(policy.posted(EventLane::Audio, true), QueuePost::Accepted);
    for (int frame = 0; frame < 9; ++frame) {
        const auto result = policy.posted(EventLane::Audio, false);
        CHECK_EQ(result, QueuePost::DroppedAudio);
        if (result == QueuePost::DroppedAudio) ++dropped;
    }
    CHECK_EQ(dropped, 9u);
    CHECK_EQ(policy.posted(EventLane::Control, true), QueuePost::Accepted);
    CHECK_EQ(policy.posted(EventLane::Control, false), QueuePost::Overflow);
    CHECK_EQ(nextEventLane(10, 11), EventLane::Control);
    CHECK_EQ(nextEventLane(12, 11), EventLane::Audio);
    CHECK_EQ(nextEventLane({}, 13), EventLane::Audio);
    CHECK_EQ(nextEventLane(14, {}), EventLane::Control);
    CHECK(!nextEventLane({}, {}));
}
