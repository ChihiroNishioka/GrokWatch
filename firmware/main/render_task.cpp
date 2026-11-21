#include "app.hpp"

#include <algorithm>
#include <cmath>

#include <M5Unified.h>
#include "esp_log.h"
#include "esp_memory_utils.h"

namespace gwapp {

namespace {

using grokwatch::faceCenter;
using grokwatch::faceRadius;
using grokwatch::screenSize;

constexpr std::uint32_t black = 0x000000;
constexpr std::uint32_t white = 0xffffff;

void drawRing(M5Canvas& sprite, const grokwatch::Ring& ring) {
    if (ring.kind == grokwatch::RingKind::None) return;

    const int outer = std::lround(ring.radius + ring.width / 2);
    const int inner = outer - std::lround(ring.width);
    if (ring.kind == grokwatch::RingKind::Solid) {
        sprite.fillArc(faceCenter, faceCenter, outer, inner, 0, 360, ring.color);
        return;
    }
    const float step = 360.0f / ring.segments;
    for (int segment = 0; segment < ring.segments; ++segment) {
        const float angle = segment * step;
        sprite.fillArc(faceCenter, faceCenter, outer, inner, angle, angle + step / 2, ring.color);
    }
}

void drawFace(M5Canvas& sprite, const grokwatch::FaceModel& face) {
    sprite.fillScreen(black);
    sprite.fillCircle(faceCenter, faceCenter, faceRadius, white);

    for (const auto& eye : face.eyes) {
        const int width = std::lround(eye.width);
        const int height = std::lround(eye.height);
        const int radius = std::min<int>(std::lround(eye.radius), std::min(width, height) / 2);
        sprite.fillRoundRect(std::lround(eye.x - eye.width / 2),
                             std::lround(eye.y - eye.height / 2),
                             width, height, radius, black);
    }

    drawRing(sprite, face.ring);
    if (face.activeDot >= 0) {
        for (int index = 0; index < static_cast<int>(face.dots.size()); ++index) {
            const auto dot = face.dots[index];
            sprite.fillCircle(dot.x, dot.y, 3, index == face.activeDot ? white : 0x404040u);
        }
    }
}

}  // namespace

void renderTask(void* context) {
    auto& app = *static_cast<App*>(context);
    M5Canvas sprite(&M5.Display);
    sprite.setColorDepth(16);
    sprite.setPsram(true);
    const auto* pixels = sprite.createSprite(screenSize, screenSize);
    if (!pixels || !esp_ptr_external_ram(pixels)) {
        ESP_LOGE("grokwatch", "sprite_allocation_failed");
        sprite.deleteSprite();
        vTaskDelete(nullptr);
        return;
    }

    const int x = (M5.Display.width() - screenSize) / 2;
    const int y = (M5.Display.height() - screenSize) / 2;
    auto deadline = xTaskGetTickCount();
    for (;;) {
        const auto frame = [&app] {
            const Lock lock(app.mutex);
            const auto now = nowMs();
            return app.face.frame(app.state, now, app.level.value(now));
        }();
        drawFace(sprite, frame);
        sprite.pushSprite(x, y);
        if (xTaskDelayUntil(&deadline, pdMS_TO_TICKS(33)) == pdFALSE) {
            vTaskDelay(1);
            deadline = xTaskGetTickCount();
        }
    }
}

}  // namespace gwapp
