#include "gw_test.hpp"
#include "grokwatch/config.hpp"
using namespace grokwatch;

TEST(config_required_values_and_default_port) {
    Config config{"wifi", "", "gateway", 8765, std::string(32, 'x')};
    CHECK_EQ(Config{}.port, 8765);
    CHECK(!Config{}.ready());
    CHECK(config.ready());
    config.token.resize(31);
    CHECK(!config.ready());
}
