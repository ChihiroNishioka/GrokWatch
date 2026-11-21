#include "app.hpp"

#include "driver/gpio.h"
#include "esp_log.h"

namespace gwapp {

void buttonTask(void* context) {
    auto& app = *static_cast<App*>(context);
    grokwatch::VolumeKeys keys;
    auto deadline = xTaskGetTickCount();
    for (;;) {
        const auto now = nowMs();
        const bool upPressed = gpio_get_level(static_cast<gpio_num_t>(grokwatch::volumeButtonUpGpio)) == 0;
        const bool downPressed = gpio_get_level(static_cast<gpio_num_t>(grokwatch::volumeButtonDownGpio)) == 0;
        bool logValue = false;
        unsigned value = 0;
        {
            Lock lock(app.mutex);
            const auto level = keys.sample(now, upPressed, downPressed, app.volume.level());
            app.volume.setLevel(level);
            logValue = keys.takeLogRequest();
            value = app.volume.value();
        }
        if (logValue) ESP_LOGI("grokwatch", "volume value=%u", value);
        vTaskDelayUntil(&deadline, pdMS_TO_TICKS(10));
    }
}

}  // namespace gwapp
