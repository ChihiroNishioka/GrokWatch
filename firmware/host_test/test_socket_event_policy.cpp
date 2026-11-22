#include "gw_test.hpp"
#include "grokwatch/socket_event_queue.hpp"
#include <cstddef>
using namespace grokwatch;

TEST(socket_events_keep_their_receive_order) {
    SocketEventQueue queue;
    SocketEvent event;
    CHECK_EQ(queue.post({SocketEventKind::Open}), QueuePost::Accepted);
    CHECK_EQ(queue.post({SocketEventKind::Audio}), QueuePost::Accepted);
    CHECK_EQ(queue.post({SocketEventKind::Text}), QueuePost::Accepted);
    CHECK(queue.receive(event));
    CHECK_EQ(event.kind, SocketEventKind::Open);
    CHECK(queue.receive(event));
    CHECK_EQ(event.kind, SocketEventKind::Audio);
    CHECK(queue.receive(event));
    CHECK_EQ(event.kind, SocketEventKind::Text);
    CHECK(!queue.receive(event));
}

TEST(audio_overflow_is_counted_and_control_events_keep_their_order) {
    SocketEventQueue queue;
    SocketEvent event;
    for (std::size_t frame = 0; frame < SocketEventQueue::maxAudioEvents; ++frame)
        CHECK_EQ(queue.post({SocketEventKind::Audio}), QueuePost::Accepted);
    for (int frame = 0; frame < 9; ++frame)
        CHECK_EQ(queue.post({SocketEventKind::Audio}), QueuePost::DroppedAudio);
    CHECK_EQ(queue.droppedAudio(), 9u);
    CHECK_EQ(queue.post({SocketEventKind::Text}), QueuePost::Accepted);
    for (std::size_t frame = 0; frame < SocketEventQueue::maxAudioEvents; ++frame) {
        CHECK(queue.receive(event));
        CHECK_EQ(event.kind, SocketEventKind::Audio);
    }
    CHECK(queue.receive(event));
    CHECK_EQ(event.kind, SocketEventKind::Text);
    CHECK(!queue.receive(event));
}

TEST(control_overflow_is_reported) {
    SocketEventQueue queue;
    for (std::size_t event = 0; event < SocketEventQueue::capacity; ++event)
        CHECK_EQ(queue.post({SocketEventKind::Text}), QueuePost::Accepted);
    CHECK_EQ(queue.post({SocketEventKind::Closed}), QueuePost::Overflow);
}
