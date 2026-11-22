#pragma once
#include "grokwatch/volume.hpp"
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
    QueueHandle_t gestures = nullptr;
    QueueHandle_t captured = nullptr;
    TaskHandle_t netTaskHandle = nullptr;
    TaskHandle_t audioTaskHandle = nullptr;
    TaskHandle_t renderTaskHandle = nullptr;
    TaskHandle_t buttonTaskHandle = nullptr;
    TaskHandle_t touchTaskHandle = nullptr;
    grokwatch::FaceAnimator face;
    grokwatch::VolumeControl volume;
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
bool configureAudio();
void renderTask(void* context);
void buttonTask(void* context);
void touchTask(void* context);
void audioTask(void* context);
void netTask(void* context);
}
