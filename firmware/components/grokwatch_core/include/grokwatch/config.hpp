#pragma once
#include <cstdint>
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

}
