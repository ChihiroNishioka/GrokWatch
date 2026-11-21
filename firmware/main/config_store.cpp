#include "config_store.hpp"
#include "nvs.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

namespace gwapp {
namespace {
std::optional<std::string> readString(nvs_handle_t handle, const char* key, size_t limit) {
    size_t size = 0;
    if (nvs_get_str(handle, key, nullptr, &size) != ESP_OK || size == 0 || size > limit + 1)
        return std::nullopt;
    std::string value(size, '\0');
    if (nvs_get_str(handle, key, value.data(), &size) != ESP_OK || size == 0)
        return std::nullopt;
    value.resize(size - 1);
    return value;
}
}

grokwatch::Config readConfig() {
    const grokwatch::Config defaults{CONFIG_GROKWATCH_WIFI_SSID, CONFIG_GROKWATCH_WIFI_PASSWORD,
        CONFIG_GROKWATCH_GATEWAY_HOST, CONFIG_GROKWATCH_GATEWAY_PORT, CONFIG_GROKWATCH_DEVICE_TOKEN};
    nvs_handle_t handle;
    if (nvs_flash_init_partition("nvs") != ESP_OK || nvs_open("grokwatch", NVS_READONLY, &handle) != ESP_OK) {
        return defaults;
    }
    grokwatch::ConfigOverrides nvs;
    nvs.ssid = readString(handle, "wifi_ssid", 32);
    nvs.password = readString(handle, "wifi_pass", 64);
    nvs.host = readString(handle, "gw_host", 253);
    nvs.token = readString(handle, "dev_token", 4095);
    uint16_t port;
    if (nvs_get_u16(handle, "gw_port", &port) == ESP_OK && port != 0) nvs.port = port;
    nvs_close(handle);
    return grokwatch::resolveConfig(defaults, nvs);
}
}
