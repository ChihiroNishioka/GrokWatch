#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace grokwatch {

inline constexpr std::size_t maxTextBytes = 4096;

constexpr bool validAudioFrame(std::size_t bytes) {
    return bytes == 640;
}

enum class Type {
    Unknown,
    Hello,
    HelloOk,
    AuthError,
    ListenStart,
    ListenStop,
    Cancel,
    State,
    TtsStart,
    TtsEnd,
    Error,
    Ping,
    Pong,
    WakeStart,
    WakeStop,
    Wake,
};

using Value = std::variant<std::string, std::int64_t, bool>;
using Field = std::pair<std::string, Value>;

struct Message {
    Type type;
    std::vector<Field> fields;
    std::string unknownType{};

    std::string_view string(std::string_view key) const;
    std::optional<std::int64_t> integer(std::string_view key) const;
    std::optional<bool> boolean(std::string_view key) const;
};

std::optional<Message> decode(std::string_view json);
std::string encode(const Message& message);

}  // namespace grokwatch
