#include "app.hpp"

#include <optional>

#include <M5Unified.h>
#include "esp_log.h"

namespace gwapp {

void touchTask(void* context) {
    auto& app = *static_cast<App*>(context);
    auto* const touch = M5.Display.touch();
    const int x = (M5.Display.width() - grokwatch::screenSize) / 2;
    const int y = (M5.Display.height() - grokwatch::screenSize) / 2;

    grokwatch::GestureDetector gesture;
    auto deadline = xTaskGetTickCount();
    for (;;) {
        m5::touch_point_t raw;
        std::optional<grokwatch::Point> point;
        // The C152 touch controller has its own I2C bus path from the QSPI display.
        if (touch->getTouchRaw(&raw, 1) != 0) {
            M5.Display.convertRawXY(&raw, 1);
            point = grokwatch::Point{raw.x - x, raw.y - y};
        }

        const auto now = nowMs();
        const auto event = gesture.update(now, point.has_value(), point);
        if (event.kind == grokwatch::Gesture::LongPress) {
            if (xQueueSend(app.longPresses, &now, pdMS_TO_TICKS(2)) != pdPASS) {
                ESP_LOGW("grokwatch", "touch_queue_full");
            }
        } else if (event.kind != grokwatch::Gesture::None) {
            const Lock lock(app.mutex);
            app.face.touch(event, nowMs());
        }
        xTaskDelayUntil(&deadline, pdMS_TO_TICKS(10));
    }
}

}  // namespace gwapp
