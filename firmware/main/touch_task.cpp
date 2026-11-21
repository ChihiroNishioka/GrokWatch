#include "app.hpp"

#include <type_traits>

#include <M5Unified.h>
#include "esp_log.h"

namespace gwapp {

void touchTask(void* context) {
    auto& app = *static_cast<App*>(context);
    const auto config = M5.Display.touch()->config();
    const int x = (M5.Display.width() - grokwatch::screenSize) / 2;
    const int y = (M5.Display.height() - grokwatch::screenSize) / 2;

    static_assert(std::is_trivially_copyable_v<grokwatch::GestureEvent>);
    grokwatch::GestureDetector gesture;
    auto deadline = xTaskGetTickCount();
    for (;;) {
        // CST816S getTouchRaw() returns zero for both release and I2C failure.
        constexpr std::uint8_t touchRegister = 0x02;
        std::uint8_t data[6]{};
        const bool read = lgfx::i2c::transactionWriteRead(config.i2c_port, config.i2c_addr,
            &touchRegister, 1, data, sizeof(data), config.freq).has_value();
        const auto contacts = read ? std::optional<unsigned>{data[0]} : std::nullopt;
        m5::touch_point_t raw{};
        raw.x = data[2] | ((data[1] & 0x0f) << 8);
        raw.y = data[4] | ((data[3] & 0x0f) << 8);
        const grokwatch::Point original{raw.x, raw.y};
        M5.Display.convertRawXY(&raw, 1);

        const auto event = gesture.sample(nowMs(), contacts, original, {raw.x - x, raw.y - y});
        if (event.kind != grokwatch::Gesture::None &&
            xQueueSend(app.gestures, &event, pdMS_TO_TICKS(2)) != pdPASS) {
            ESP_LOGW("grokwatch", "touch_queue_full");
        }
        xTaskDelayUntil(&deadline, pdMS_TO_TICKS(10));
    }
}

}  // namespace gwapp
