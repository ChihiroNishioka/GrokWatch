#include "config_store.hpp"
#include "sdkconfig.h"

namespace gwapp {

grokwatch::Config readConfig() {
    return {CONFIG_GROKWATCH_WIFI_SSID, CONFIG_GROKWATCH_WIFI_PASSWORD,
            CONFIG_GROKWATCH_GATEWAY_HOST, CONFIG_GROKWATCH_GATEWAY_PORT,
            CONFIG_GROKWATCH_DEVICE_TOKEN};
}

}
