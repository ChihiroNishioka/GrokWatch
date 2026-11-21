#pragma once

#include <cstdint>
#include <optional>

namespace grokwatch {

enum class EventLane { Control, Audio };
enum class QueuePost { Accepted, DroppedAudio, Overflow };

inline std::optional<EventLane> nextEventLane(std::optional<std::uint64_t> control,
                                              std::optional<std::uint64_t> audio) {
    if (!control && !audio) return {};
    if (!audio) return EventLane::Control;
    if (!control || *audio < *control) return EventLane::Audio;
    return EventLane::Control;
}

class SocketEventPolicy {
public:
    QueuePost posted(EventLane lane, bool accepted) const {
        if (accepted) return QueuePost::Accepted;
        return lane == EventLane::Audio ? QueuePost::DroppedAudio : QueuePost::Overflow;
    }
};

}
