#include "app.hpp"

#include <M5Unified.h>

namespace gwapp {

bool initBoard() {
    auto config = M5.config();
    config.fallback_board = m5::board_t::board_unknown;
    config.external_display_value = 0;
    config.output_power = false;
    config.internal_imu = false;
    config.internal_rtc = false;
    config.internal_mic = true;
    config.internal_spk = true;
    M5.begin(config);

    if (M5.getBoard() != m5::board_t::board_M5StopWatch ||
        !M5.Display.touch() || !M5.Mic.isEnabled() || !M5.Speaker.isEnabled()) {
        return false;
    }

    M5.Display.setRotation(0);
    return M5.Display.width() >= grokwatch::screenSize &&
           M5.Display.height() >= grokwatch::screenSize;
}

}  // namespace gwapp
