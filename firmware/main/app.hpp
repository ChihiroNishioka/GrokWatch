#pragma once
#include "grokwatch/face_model.hpp"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

namespace gwapp {
struct Captured {
    grokwatch::PcmFrame pcm;
    unsigned epoch;
};

struct App {
    App(std::uint32_t seed, grokwatch::Millis now) : face(seed, now) {}

    SemaphoreHandle_t mutex = nullptr;
    QueueHandle_t longPresses = nullptr;
    QueueHandle_t captured = nullptr;
    grokwatch::FaceAnimator face;
    grokwatch::State state = grokwatch::State::Disconnected;
    bool capturing = false;
    unsigned captureEpoch = 0;
    grokwatch::PlaybackBuffer playback;
    unsigned playbackEpoch = 0;
    bool canPlay = false;
    bool playbackDrained = false;
    bool audioFault = false;
    grokwatch::AudioLevel level;
};

class Lock {
public:
    explicit Lock(SemaphoreHandle_t mutex) : mutex_(mutex) { xSemaphoreTake(mutex_, portMAX_DELAY); }
    ~Lock() { xSemaphoreGive(mutex_); }
    Lock(const Lock&) = delete;
    Lock& operator=(const Lock&) = delete;

private:
    SemaphoreHandle_t mutex_;
};

inline grokwatch::Millis nowMs() { return esp_timer_get_time() / 1000; }

bool initBoard();
void renderTask(void* context);
void touchTask(void* context);
void audioTask(void* context);
void netTask(void* context);
}
