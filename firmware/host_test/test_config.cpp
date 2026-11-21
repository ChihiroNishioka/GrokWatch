#include "gw_test.hpp"
#include "grokwatch/config.hpp"
using namespace grokwatch;

TEST(config_precedence_and_missing) {
    Config defaults{"wifi", "pass", "gateway", 8765, std::string(32, 'x')};
    ConfigOverrides nvs;
    nvs.ssid = "override";
    nvs.port = 9000;
    auto config = resolveConfig(defaults, nvs);
    CHECK_EQ(config.ssid, "override");
    CHECK_EQ(config.password, "pass");
    CHECK_EQ(config.port, 9000);
    CHECK(config.ready());
    config = resolveConfig(defaults, {});
    CHECK_EQ(config.ssid, "wifi");
    CHECK_EQ(config.port, 8765);
    CHECK_EQ(Config{}.port, 8765);
    CHECK(!Config{}.ready());
    nvs.host = "";
    CHECK(!resolveConfig(defaults, nvs).ready());
    defaults.token.resize(31);
    CHECK(!defaults.ready());
}
