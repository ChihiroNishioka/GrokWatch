#include "grokwatch/protocol.hpp"

#include <algorithm>
#include <array>
#include <charconv>

namespace grokwatch {
namespace {

const Value* find(const std::vector<Field>& fields, std::string_view key) {
    const auto field = std::find_if(fields.begin(), fields.end(), [key](const Field& entry) {
        return entry.first == key;
    });
    return field == fields.end() ? nullptr : &field->second;
}

bool validCodePoint(std::uint32_t point) {
    return point <= 0x10ffff && (point < 0xd800 || point > 0xdfff);
}

bool validUtf8(std::string_view text) {
    for (std::size_t i = 0; i < text.size();) {
        const auto first = static_cast<unsigned char>(text[i++]);
        if (first < 0x80) continue;
        if (first < 0xc2 || first > 0xf4) return false;

        const unsigned length = first < 0xe0 ? 2 : first < 0xf0 ? 3 : 4;
        constexpr std::array<std::uint32_t, 5> minimum{0, 0, 0x80, 0x800, 0x10000};
        std::uint32_t point = first & (0xffu >> (length + 1));
        for (unsigned j = 1; j < length; ++j) {
            if (i == text.size()) return false;
            const auto next = static_cast<unsigned char>(text[i++]);
            if ((next & 0xc0) != 0x80) return false;
            point = (point << 6) | (next & 0x3f);
        }
        if (point < minimum[length] || !validCodePoint(point)) return false;
    }
    return true;
}

void appendUtf8(std::string& text, std::uint32_t point) {
    if (point < 0x80) {
        text.push_back(static_cast<char>(point));
        return;
    }

    const unsigned length = point < 0x800 ? 2 : point < 0x10000 ? 3 : 4;
    constexpr std::array<unsigned, 5> prefix{0, 0, 0xc0, 0xe0, 0xf0};
    text.push_back(static_cast<char>(prefix[length] | (point >> (6 * (length - 1)))));
    for (unsigned remaining = length - 1; remaining > 0; --remaining) {
        const auto byte = (point >> (6 * (remaining - 1))) & 0x3f;
        text.push_back(static_cast<char>(0x80 | byte));
    }
}

constexpr std::string_view escaped = "\"\\/\b\f\n\r\t";
constexpr std::string_view escapes = "\"\\/bfnrt";
constexpr std::string_view hexDigits = "0123456789abcdef";

void appendQuoted(std::string& output, std::string_view text) {
    output += '"';
    for (const unsigned char byte : text) {
        const auto escape = escaped.find(static_cast<char>(byte));
        if (escape != std::string_view::npos && byte != '/') {
            output += '\\';
            output += escapes[escape];
        } else if (byte < 0x20) {
            output += "\\u00";
            output += hexDigits[byte >> 4];
            output += hexDigits[byte & 0xf];
        } else {
            output += static_cast<char>(byte);
        }
    }
    output += '"';
}

class Parser {
public:
    explicit Parser(std::string_view input) : remaining_(input) {}

    std::optional<std::vector<Field>> object() {
        if (!take('{')) return {};
        std::vector<Field> fields;
        if (!take('}')) {
            do {
                auto key = quoted();
                if (!key || find(fields, *key) || !take(':')) return {};
                auto item = value();
                if (!item) return {};
                fields.emplace_back(std::move(*key), std::move(*item));
            } while (take(','));
            if (!take('}')) return {};
        }
        skipWhitespace();
        if (!remaining_.empty()) return {};
        return fields;
    }

private:
    std::string_view remaining_;

    void skipWhitespace() {
        const auto start = remaining_.find_first_not_of(" \n\r\t");
        remaining_.remove_prefix(start == std::string_view::npos ? remaining_.size() : start);
    }

    bool take(char ch) {
        skipWhitespace();
        if (remaining_.empty() || remaining_.front() != ch) return false;
        remaining_.remove_prefix(1);
        return true;
    }

    bool literal(std::string_view word) {
        if (remaining_.substr(0, word.size()) != word) return false;
        remaining_.remove_prefix(word.size());
        return true;
    }

    std::optional<std::uint32_t> hexQuad() {
        if (remaining_.size() < 4) return {};
        std::uint32_t point = 0;
        for (char digit : remaining_.substr(0, 4)) {
            if (digit >= 'A' && digit <= 'F') digit += 'a' - 'A';
            const auto index = hexDigits.find(digit);
            if (index == std::string_view::npos) return {};
            point = (point << 4) | static_cast<std::uint32_t>(index);
        }
        remaining_.remove_prefix(4);
        return point;
    }

    bool escape(std::string& text) {
        if (remaining_.empty()) return false;
        const auto code = remaining_.front();
        remaining_.remove_prefix(1);
        const auto index = escapes.find(code);
        if (index != std::string_view::npos) {
            text += escaped[index];
            return true;
        }
        if (code != 'u') return false;

        auto point = hexQuad();
        if (!point) return false;
        if (*point >= 0xd800 && *point <= 0xdbff) {
            if (!literal("\\u")) return false;
            const auto low = hexQuad();
            if (!low || *low < 0xdc00 || *low > 0xdfff) return false;
            *point = 0x10000 + ((*point - 0xd800) << 10) + (*low - 0xdc00);
        }
        if (!validCodePoint(*point)) return false;
        appendUtf8(text, *point);
        return true;
    }

    std::optional<std::string> quoted() {
        if (!take('"')) return {};
        std::string text;
        while (!remaining_.empty()) {
            const auto byte = static_cast<unsigned char>(remaining_.front());
            remaining_.remove_prefix(1);
            if (byte == '"') return text;
            if (byte < 0x20) return {};
            if (byte == '\\') {
                if (!escape(text)) return {};
            } else {
                text += static_cast<char>(byte);
            }
        }
        return {};
    }

    std::optional<Value> value() {
        skipWhitespace();
        if (remaining_.empty()) return {};
        if (remaining_.front() == '"') {
            auto text = quoted();
            if (!text) return {};
            return Value{std::move(*text)};
        }
        if (literal("true")) return Value{true};
        if (literal("false")) return Value{false};

        const auto digits = remaining_.front() == '-' ? remaining_.substr(1) : remaining_;
        if (digits.size() > 1 && digits[0] == '0' && digits[1] >= '0' && digits[1] <= '9') {
            return {};
        }
        std::int64_t number = 0;
        const auto begin = remaining_.data();
        const auto parsed = std::from_chars(begin, begin + remaining_.size(), number);
        if (parsed.ec != decltype(parsed.ec){}) return {};
        remaining_.remove_prefix(static_cast<std::size_t>(parsed.ptr - begin));
        return Value{number};
    }
};

struct MessageName {
    Type type;
    std::string_view text;
};

constexpr MessageName names[] = {
    {Type::Hello, "hello"},
    {Type::HelloOk, "hello_ok"},
    {Type::AuthError, "auth_error"},
    {Type::ListenStart, "listen_start"},
    {Type::ListenStop, "listen_stop"},
    {Type::Cancel, "cancel"},
    {Type::State, "state"},
    {Type::TtsStart, "tts_start"},
    {Type::TtsEnd, "tts_end"},
    {Type::Error, "error"},
    {Type::Ping, "ping"},
    {Type::Pong, "pong"},
};

bool hasFields(const Message& message) {
    switch (message.type) {
        case Type::Hello:
            return message.integer("v").has_value()
                && std::get_if<std::string>(find(message.fields, "token"))
                && std::get_if<std::string>(find(message.fields, "fw"));
        case Type::HelloOk:
            return message.integer("v") == 1;
        case Type::AuthError: {
            const auto code = message.string("code");
            return code == "bad_token" || code == "unsupported_version";
        }
        case Type::State: {
            const auto state = message.string("state");
            return state == "idle" || state == "listening" || state == "thinking"
                || state == "speaking" || state == "error";
        }
        case Type::TtsStart:
            return message.integer("sample_rate") == 16000;
        case Type::Error:
            return std::get_if<std::string>(find(message.fields, "code"))
                && message.boolean("retryable").has_value();
        case Type::Ping:
        case Type::Pong:
            return message.integer("t").has_value();
        case Type::Unknown:
        case Type::ListenStart:
        case Type::ListenStop:
        case Type::Cancel:
        case Type::TtsEnd:
            return true;
    }
    return false;
}

}  // namespace

std::string_view Message::string(std::string_view key) const {
    const auto* value = std::get_if<std::string>(find(fields, key));
    return value ? std::string_view(*value) : std::string_view{};
}

std::optional<std::int64_t> Message::integer(std::string_view key) const {
    const auto* value = std::get_if<std::int64_t>(find(fields, key));
    return value ? std::optional{*value} : std::nullopt;
}

std::optional<bool> Message::boolean(std::string_view key) const {
    const auto* value = std::get_if<bool>(find(fields, key));
    return value ? std::optional{*value} : std::nullopt;
}

std::optional<Message> decode(std::string_view json) {
    if (json.size() > maxTextBytes || !validUtf8(json)) return {};
    auto fields = Parser(json).object();
    if (!fields) return {};
    const auto typeField = std::find_if(fields->begin(), fields->end(), [](const Field& field) {
        return field.first == "type";
    });
    if (typeField == fields->end()) return {};
    auto* type = std::get_if<std::string>(&typeField->second);
    if (!type) return {};

    Message message{Type::Unknown, {}};
    for (const auto& name : names) {
        if (name.text == *type) {
            message.type = name.type;
            break;
        }
    }
    if (message.type == Type::Unknown) message.unknownType = std::move(*type);
    fields->erase(typeField);
    message.fields = std::move(*fields);
    if (!hasFields(message)) return {};
    return message;
}

std::string encode(const Message& message) {
    if (!hasFields(message)) return {};
    std::string_view type = message.unknownType;
    for (const auto& name : names) {
        if (name.type == message.type) {
            type = name.text;
            break;
        }
    }

    std::string json = "{\"type\":";
    appendQuoted(json, type);
    for (std::size_t i = 0; i < message.fields.size(); ++i) {
        const auto& [key, value] = message.fields[i];
        if (key == "type") return {};
        for (std::size_t j = 0; j < i; ++j) {
            if (message.fields[j].first == key) return {};
        }
        json += ',';
        appendQuoted(json, key);
        json += ':';
        if (const auto* str = std::get_if<std::string>(&value)) {
            appendQuoted(json, *str);
        } else if (const auto* number = std::get_if<std::int64_t>(&value)) {
            json += std::to_string(*number);
        } else {
            json += std::get<bool>(value) ? "true" : "false";
        }
        if (json.size() >= maxTextBytes) return {};
    }
    json += '}';
    if (json.size() > maxTextBytes || !validUtf8(json)) return {};
    return json;
}

}  // namespace grokwatch
