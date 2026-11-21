#include "app.hpp"
#include "esp_log.h"
#include "esp_random.h"
#include <type_traits>

using namespace gwapp;

extern "C" void app_main() {
    static_assert(std::is_trivially_copyable_v<Captured>);

    esp_log_level_set("*", ESP_LOG_NONE);
    esp_log_level_set("grokwatch", ESP_LOG_INFO);
    if (!initBoard()) {
        ESP_LOGE("grokwatch", "board_init_failed");
        return;
    }

    static App app(esp_random(), nowMs());
    app.mutex = xSemaphoreCreateMutex();
    app.gestures = xQueueCreate(16, sizeof(grokwatch::GestureEvent));
    app.captured = xQueueCreate(12, sizeof(Captured));
    if (!app.mutex || !app.gestures || !app.captured) {
        ESP_LOGE("grokwatch", "allocation_failed");
        return;
    }

    if (xTaskCreate(buttonTask, "buttons", 3072, &app, 5, nullptr) != pdPASS ||
        xTaskCreate(renderTask, "render", 6144, &app, 4, nullptr) != pdPASS ||
        xTaskCreate(touchTask, "touch", 4096, &app, 5, nullptr) != pdPASS ||
        xTaskCreate(audioTask, "audio", 6144, &app, 6, nullptr) != pdPASS ||
        xTaskCreate(netTask, "net", 12288, &app, 5, nullptr) != pdPASS) {
        ESP_LOGE("grokwatch", "task_start_failed");
    }
}
