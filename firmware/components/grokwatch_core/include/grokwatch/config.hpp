#pragma once
#include <cstdint>
#include <optional>
#include <string>

namespace grokwatch {

struct Config {
    std::string ssid;
    std::string password;
    std::string host;
    std::uint16_t port = 8765;
    std::string token;

    bool ready() const {
        return !ssid.empty() && !host.empty() && port != 0 && token.size() >= 32;
    }
};

struct ConfigOverrides {
    std::optional<std::string> ssid;
    std::optional<std::string> password;
    std::optional<std::string> host;
    std::optional<std::uint16_t> port;
    std::optional<std::string> token;
};

inline Config resolveConfig(const Config& defaults, const ConfigOverrides& nvs) {
    return {nvs.ssid.value_or(defaults.ssid), nvs.password.value_or(defaults.password),
            nvs.host.value_or(defaults.host), nvs.port.value_or(defaults.port),
            nvs.token.value_or(defaults.token)};
}

}
