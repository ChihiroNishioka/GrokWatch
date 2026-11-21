#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace grokwatch {

enum class SocketEventKind : std::uint8_t { Open, Closed, Text, Audio, BadText, Activity };

struct SocketEvent {
    SocketEventKind kind;
    char* data = nullptr;
    std::size_t size = 0;
};

enum class QueuePost { Accepted, DroppedAudio, Overflow };

class SocketEventQueue {
public:
    static constexpr std::size_t capacity = 64;
    static constexpr std::size_t maxAudioEvents = 32;

    QueuePost post(SocketEvent event) {
        if (event.kind == SocketEventKind::Audio && (audioSize_ == maxAudioEvents || size_ == capacity)) {
            ++droppedAudio_;
            return QueuePost::DroppedAudio;
        }
        if (size_ == capacity) return QueuePost::Overflow;

        events_[write_] = event;
        write_ = (write_ + 1) % capacity;
        ++size_;
        if (event.kind == SocketEventKind::Audio) ++audioSize_;
        return QueuePost::Accepted;
    }

    bool receive(SocketEvent& event) {
        if (size_ == 0) return false;

        event = events_[read_];
        read_ = (read_ + 1) % capacity;
        --size_;
        if (event.kind == SocketEventKind::Audio) --audioSize_;
        return true;
    }

    std::uint32_t droppedAudio() const { return droppedAudio_; }

private:
    std::array<SocketEvent, capacity> events_{};
    std::size_t read_ = 0;
    std::size_t write_ = 0;
    std::size_t size_ = 0;
    std::size_t audioSize_ = 0;
    std::uint32_t droppedAudio_ = 0;
};

}
