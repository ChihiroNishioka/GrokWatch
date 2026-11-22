#include "app.hpp"
#include "grokwatch/avatar_scale.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

#include <M5Unified.h>
#include "esp_log.h"
#include "esp_memory_utils.h"

namespace gwapp {

namespace {

using grokwatch::faceCenter;
using grokwatch::screenSize;

constexpr std::uint32_t black = 0x000000;
constexpr std::uint32_t white = 0xffffff;

void drawRing(M5Canvas& sprite, const grokwatch::DrawnRing& ring) {
    if (ring.kind == grokwatch::RingKind::None) return;

    const int outer = std::lround(ring.radius + ring.width / 2);
    const int inner = outer - std::lround(ring.width);
    if (ring.kind == grokwatch::RingKind::Solid) {
        sprite.fillArc(faceCenter, faceCenter, outer, inner, 0, 360, ring.color);
        return;
    }
    if (ring.kind == grokwatch::RingKind::Arc) {
        sprite.fillArc(faceCenter, faceCenter, outer, inner, static_cast<float>(ring.start),
                       static_cast<float>(ring.start + ring.sweep), ring.color);
        return;
    }
    const float step = 360.0f / ring.segments;
    for (int segment = 0; segment < ring.segments; ++segment) {
        const float angle = segment * step;
        sprite.fillArc(faceCenter, faceCenter, outer, inner, angle, angle + step / 2, ring.color);
    }
}

// Paints the eyelids over an already drawn eye. The inner side faces the face center.
void drawLids(M5Canvas& sprite, const grokwatch::Eye& eye, bool leftEye) {
    if (eye.lidInner <= 0 && eye.lidOuter <= 0 && eye.lidBottom <= 0) return;
    const int left = std::lround(eye.x - eye.width / 2);
    const int right = std::lround(eye.x + eye.width / 2);
    const int top = std::lround(eye.y - eye.height / 2);
    const int bottom = std::lround(eye.y + eye.height / 2);
    sprite.setClipRect(left, top, right - left + 1, bottom - top + 1);
    if (eye.lidInner > 0 || eye.lidOuter > 0) {
        const int innerX = leftEye ? right : left;
        const int outerX = leftEye ? left : right;
        const int innerY = top + std::lround(eye.height * eye.lidInner);
        const int outerY = top + std::lround(eye.height * eye.lidOuter);
        sprite.fillTriangle(innerX, top, outerX, top, outerX, outerY, white);
        sprite.fillTriangle(innerX, top, outerX, outerY, innerX, innerY, white);
    }
    if (eye.lidBottom > 0) {
        const int ry = std::lround(0.9 * eye.height);
        const int centerY = bottom - std::lround(eye.height * eye.lidBottom) + ry;
        sprite.fillEllipse(std::lround(eye.x), centerY, std::lround(1.2 * eye.width), ry, white);
    }
    sprite.clearClipRect();
}

void drawFace(M5Canvas& sprite, const grokwatch::FaceModel& face, double scale) {
    const auto drawn = grokwatch::scaleFace(face, scale);
    sprite.fillScreen(black);
    sprite.fillCircle(faceCenter, faceCenter, std::lround(drawn.radius), white);

    for (std::size_t index = 0; index < drawn.eyes.size(); ++index) {
        const auto& eye = drawn.eyes[index];
        const int width = std::lround(eye.width);
        const int height = std::lround(eye.height);
        const int radius = std::min<int>(std::lround(eye.radius), std::min(width, height) / 2);
        sprite.fillRoundRect(std::lround(eye.x - eye.width / 2),
                             std::lround(eye.y - eye.height / 2),
                             width, height, radius, black);
        drawLids(sprite, eye, index == 0);
    }

    drawRing(sprite, drawn.ring);
    if (drawn.activeDot >= 0) {
        for (int index = 0; index < static_cast<int>(drawn.dots.size()); ++index) {
            const auto dot = drawn.dots[index];
            sprite.fillCircle(std::lround(dot.x), std::lround(dot.y), drawn.dotRadius,
                              index == drawn.activeDot ? white : 0x404040u);
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
            const auto level = app.state == grokwatch::State::Listening ? app.micLevel.value(now)
                                                                         : app.level.value(now);
            return std::pair{app.face.frame(app.state, now, level), app.volume.value()};
        }();
        drawFace(sprite, frame.first, grokwatch::avatarScale(frame.second));
        sprite.pushSprite(x, y);
        if (xTaskDelayUntil(&deadline, pdMS_TO_TICKS(33)) == pdFALSE) {
            vTaskDelay(1);
            deadline = xTaskGetTickCount();
        }
    }
}

}  // namespace gwapp
