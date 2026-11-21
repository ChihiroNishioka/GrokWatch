#include "app.hpp"
#include "config_store.hpp"
#include "grokwatch/link_supervisor.hpp"
#include "grokwatch/protocol.hpp"
#include "grokwatch/socket_event_policy.hpp"

#include "esp_app_desc.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_websocket_client.h"
#include "esp_wifi.h"

#include <array>
#include <atomic>
#include <cstring>
#include <memory>
#include <new>

#if defined(CONFIG_ESP_WIFI_NVS_ENABLED) || defined(CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE)
#error "GrokWatch requires Wi-Fi and PHY NVS storage to be disabled"
#endif

namespace gwapp {
namespace {
using namespace grokwatch;
constexpr auto tag = "grokwatch";

struct WifiEvents {
    // Bit 0 holds IP availability. Every loss increments the upper bits.
    std::atomic<unsigned> status{0};
};

void wifiEvent(void* context, esp_event_base_t base, int32_t id, void*) {
    auto& status = static_cast<WifiEvents*>(context)->status;
    const auto old = status.load();
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        status.store(old | 1u);
    } else if ((base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) ||
               (base == IP_EVENT && id == IP_EVENT_STA_LOST_IP)) {
        status.store((old & ~1u) + 2u);
    }
}

bool startWifi(const Config& config, WifiEvents& events) {
    wifi_config_t sta{};
    if (config.ssid.size() > sizeof(sta.sta.ssid) ||
        config.password.size() > sizeof(sta.sta.password)) return false;
    std::memcpy(sta.sta.ssid, config.ssid.data(), config.ssid.size());
    std::memcpy(sta.sta.password, config.password.data(), config.password.size());
    sta.sta.threshold.authmode = config.password.empty() ? WIFI_AUTH_OPEN : WIFI_AUTH_WPA2_PSK;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = false;

    return esp_netif_init() == ESP_OK && esp_event_loop_create_default() == ESP_OK &&
           esp_netif_create_default_wifi_sta() != nullptr &&
           esp_wifi_init(&init) == ESP_OK &&
           esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, wifiEvent, &events) == ESP_OK &&
           esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, wifiEvent, &events) == ESP_OK &&
           esp_wifi_set_storage(WIFI_STORAGE_RAM) == ESP_OK &&
           esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK &&
           esp_wifi_set_config(WIFI_IF_STA, &sta) == ESP_OK && esp_wifi_start() == ESP_OK;
}

enum class SocketKind { Open, Closed, Text, Audio, BadText, Activity };
struct SocketEvent {
    SocketKind kind;
    char* data = nullptr;
    std::size_t size = 0;
    std::uint64_t sequence = 0;
};

class Socket {
public:
    Socket(QueueHandle_t controls, QueueHandle_t audio)
        : controls_(controls), audio_(audio) {}

    bool open(const Config& config) {
        esp_websocket_client_config_t ws{};
        ws.host = config.host.c_str();
        ws.port = config.port;
        ws.path = "/v1/ws";
        ws.transport = WEBSOCKET_TRANSPORT_OVER_TCP;
        ws.disable_auto_reconnect = true;
        ws.disable_pingpong_discon = true;
        ws.network_timeout_ms = 2000;
        ws.task_stack = 6144;
        ws.buffer_size = 1024;
        handle_ = esp_websocket_client_init(&ws);
        return handle_ && esp_websocket_register_events(handle_, WEBSOCKET_EVENT_ANY, onEvent, this) == ESP_OK &&
               esp_websocket_client_start(handle_) == ESP_OK;
    }

    void close() {
        if (handle_) esp_websocket_client_destroy(handle_);
        handle_ = nullptr;
        SocketEvent event;
        while (receive(event)) delete[] event.data;
        opcode_ = 0;
        used_ = 0;
        oversize_ = false;
        overflow_.store(false);
    }

    bool sendText(const Message& message) {
        const auto json = encode(message);
        return handle_ && !json.empty() &&
               esp_websocket_client_send_text(handle_, json.data(), json.size(), pdMS_TO_TICKS(100)) ==
                   static_cast<int>(json.size());
    }

    bool sendAudio(const PcmFrame& frame) {
        static_assert(sizeof(PcmFrame) == bytesPerFrame);
        return handle_ && esp_websocket_client_send_bin(handle_,
            reinterpret_cast<const char*>(frame.data()), bytesPerFrame,
            pdMS_TO_TICKS(100)) == static_cast<int>(bytesPerFrame);
    }

    bool receive(SocketEvent& event) {
        if (!controls_ || !audio_) return false;
        SocketEvent control;
        SocketEvent audio;
        const bool hasControl = xQueuePeek(controls_, &control, 0) == pdTRUE;
        const bool hasAudio = xQueuePeek(audio_, &audio, 0) == pdTRUE;
        const auto lane = nextEventLane(
            hasControl ? std::optional{control.sequence} : std::nullopt,
            hasAudio ? std::optional{audio.sequence} : std::nullopt);
        if (!lane) return false;
        const auto queue = *lane == EventLane::Control ? controls_ : audio_;
        return xQueueReceive(queue, &event, 0) == pdTRUE;
    }

    bool overflow() const { return overflow_.load(); }
    std::uint32_t droppedAudio() const { return droppedAudio_.load(std::memory_order_relaxed); }

private:
    static void onEvent(void* context, esp_event_base_t, int32_t id, void* data) {
        auto& socket = *static_cast<Socket*>(context);
        switch (id) {
            case WEBSOCKET_EVENT_CONNECTED: socket.post({SocketKind::Open}); break;
            case WEBSOCKET_EVENT_DISCONNECTED:
            case WEBSOCKET_EVENT_CLOSED:
            case WEBSOCKET_EVENT_FINISH: socket.post({SocketKind::Closed}); break;
            case WEBSOCKET_EVENT_DATA:
                socket.fragment(*static_cast<const esp_websocket_event_data_t*>(data));
                break;
            default: break;
        }
    }

    void post(SocketEvent event) {
        const auto lane = event.kind == SocketKind::Audio ? EventLane::Audio : EventLane::Control;
        event.sequence = sequence_.fetch_add(1, std::memory_order_relaxed);
        const auto queue = lane == EventLane::Audio ? audio_ : controls_;
        const bool queued = queue && xQueueSend(queue, &event, 0) == pdTRUE;
        const auto result = policy_.posted(lane, queued);
        if (result != QueuePost::Accepted) {
            delete[] event.data;
            if (result == QueuePost::DroppedAudio)
                droppedAudio_.fetch_add(1, std::memory_order_relaxed);
            else
                overflow_.store(true);
        }
    }

    void fragment(const esp_websocket_event_data_t& frame) {
        constexpr int text = 1;
        constexpr int binary = 2;
        if (frame.op_code >= 8) {
            post({SocketKind::Activity});
            return;
        }
        if (frame.payload_offset == 0 && frame.op_code != 0) {
            opcode_ = frame.op_code;
            used_ = 0;
            oversize_ = false;
        }
        if (opcode_ != text && opcode_ != binary) return;

        const auto limit = opcode_ == text ? maxTextBytes : bytesPerFrame;
        if (frame.data_len > 0 && !oversize_) {
            const auto count = static_cast<std::size_t>(frame.data_len);
            if (count > limit - used_) {
                oversize_ = true;
            } else {
                std::memcpy(buffer_.data() + used_, frame.data_ptr, count);
                used_ += count;
            }
        }
        if (frame.data_len != frame.payload_len - frame.payload_offset || !frame.fin) return;

        if (oversize_ || (opcode_ == binary && !validAudioFrame(used_))) {
            post({opcode_ == text ? SocketKind::BadText : SocketKind::Activity});
        } else {
            auto data = new (std::nothrow) char[used_ ? used_ : 1];
            if (data) {
                std::memcpy(data, buffer_.data(), used_);
                post({opcode_ == text ? SocketKind::Text : SocketKind::Audio, data, used_});
            } else {
                overflow_.store(true);
            }
        }
        opcode_ = 0;
    }

    QueueHandle_t controls_;
    QueueHandle_t audio_;
    esp_websocket_client_handle_t handle_ = nullptr;
    std::atomic<bool> overflow_{false};
    std::atomic<std::uint64_t> sequence_{0};
    std::atomic<std::uint32_t> droppedAudio_{0};
    SocketEventPolicy policy_;
    std::array<char, maxTextBytes> buffer_{};
    int opcode_ = 0;
    std::size_t used_ = 0;
    bool oversize_ = false;
};

State decodeState(std::string_view state) {
    if (state == "listening") return State::Listening;
    if (state == "thinking") return State::Thinking;
    if (state == "speaking") return State::Speaking;
    if (state == "error") return State::Error;
    return State::Idle;
}

class Network {
public:
    Network(App& app, QueueHandle_t controls, QueueHandle_t audio, Config config)
        : app_(app), socket_(controls, audio), config_(std::move(config)), rng_(esp_random()) {}

    void run(bool hasQueue) {
        const bool configured = config_.ready();
        const bool wifiStarted = configured && hasQueue && startWifi(config_, wifiEvents_);
        if (!configured) ESP_LOGI(tag, "設定なし");
        else if (!wifiStarted) ESP_LOGE(tag, "network_init_failed");

        while (true) {
            auto now = nowMs();
            if (wifiStarted) {
                pollWifi(now);
                pollSocket();
                now = nowMs();
                linkAction(link_.tick(now, rng_.unit()), now);
            }

            for (GestureEvent event; xQueueReceive(app_.gestures, &event, 0) == pdTRUE;) {
                const auto at = nowMs();
                apply(avatar_.touch(event, at));
                if (event.kind != Gesture::LongPress) {
                    const Lock lock(app_.mutex);
                    app_.face.touch(event, at);
                }
            }
            capture();
            const bool audioFault = pollPlayback();
            now = nowMs();
            if (audioFault || ioFailed_) linkAction(link_.failed(now, rng_.unit()), now);
            apply(avatar_.tick(now));
            vTaskDelay(pdMS_TO_TICKS(5));
        }
    }

private:
    void pollWifi(Millis now) {
        const auto status = wifiEvents_.status.load();
        if ((status & ~1u) != (wifiStatus_ & ~1u)) {
            linkAction(link_.wifi(false, now), now);
            wifiNext_ = now + wifiBackoff_.next(rng_.unit());
        }
        wifiStatus_ = status;
        const bool hasIp = status & 1u;
        linkAction(link_.wifi(hasIp, now), now);
        if (hasIp) {
            wifiBackoff_.reset();
            wifiNext_ = 0;
        } else if (now >= wifiNext_) {
            // A lost-IP event can arrive while the station remains associated.
            esp_wifi_disconnect();
            if (esp_wifi_connect() == ESP_OK) wifiNext_ = now + 20000;
            else wifiNext_ = now + wifiBackoff_.next(rng_.unit());
        }
    }

    void pollSocket() {
        SocketEvent event;
        for (int i = 0; i < 32 && socket_.receive(event); ++i) {
            std::unique_ptr<char[]> data(event.data);
            const auto now = nowMs();
            switch (event.kind) {
                case SocketKind::Open: linkAction(link_.opened(now), now); break;
                case SocketKind::Closed: linkAction(link_.failed(now, rng_.unit()), now); break;
                case SocketKind::BadText:
                    link_.received(now);
                    badMessage();
                    break;
                case SocketKind::Activity: link_.received(now); break;
                case SocketKind::Text:
                    link_.received(now);
                    receiveText({data.get(), event.size}, now);
                    break;
                case SocketKind::Audio:
                    link_.received(now);
                    if (link_.ready() && avatar_.acceptsPlayback()) {
                        PcmFrame frame;
                        std::memcpy(frame.data(), data.get(), bytesPerFrame);
                        Lock lock(app_.mutex);
                        app_.playback.push(frame);
                    } else if (!link_.ready()) {
                        ioFailed_ = true;
                    }
                    break;
            }
            if (ioFailed_) break;
        }
        const auto droppedAudio = socket_.droppedAudio();
        if (droppedAudio != reportedDroppedAudio_) {
            ESP_LOGW(tag, "audio_queue_frames_dropped=%u",
                     static_cast<unsigned>(droppedAudio - reportedDroppedAudio_));
            reportedDroppedAudio_ = droppedAudio;
        }
        if (socket_.overflow()) ioFailed_ = true;
    }

    void linkAction(LinkAction action, Millis now) {
        switch (action) {
            case LinkAction::None: break;
            case LinkAction::Connect:
                if (!socket_.open(config_)) linkAction(link_.failed(now, rng_.unit()), now);
                break;
            case LinkAction::Hello:
                send({Type::Hello, {{"v", 1}, {"token", config_.token},
                                     {"fw", esp_app_get_description()->version}}});
                break;
            case LinkAction::Ready: apply(avatar_.hello(now)); break;
            case LinkAction::Ping: send({Type::Ping, {{"t", now}}}); break;
            case LinkAction::Disconnect:
                apply(avatar_.linkDown(now));
                socket_.close();
                ioFailed_ = false;
                break;
        }
    }

    void send(const Message& message) {
        if (!ioFailed_ && !socket_.sendText(message)) ioFailed_ = true;
    }

    void badMessage() {
        if (link_.ready()) send({Type::Error, {{"code", "bad_message"}, {"retryable", false}}});
        else ioFailed_ = true;
    }

    void receiveText(std::string_view json, Millis now) {
        const auto message = decode(json);
        if (!message) {
            badMessage();
            return;
        }
        if (!link_.ready()) {
            if (message->type == Type::HelloOk) linkAction(link_.authenticated(now), now);
            else if (message->type == Type::AuthError) linkAction(link_.reject(now), now);
            else ioFailed_ = true;
            return;
        }
        switch (message->type) {
            case Type::State:
                apply(avatar_.remote(decodeState(message->string("state")), now, message->integer("session")));
                break;
            case Type::Error:
                apply(avatar_.error(message->string("code") == "no_speech",
                                    message->boolean("retryable").value_or(false), now,
                                    message->integer("session")));
                break;
            case Type::TtsStart:
                avatar_.ttsStart(now);
                if (avatar_.acceptsPlayback()) {
                    Lock lock(app_.mutex);
                    resetPlayback();
                    app_.playback.start();
                    publish({});
                }
                break;
            case Type::TtsEnd:
                if (avatar_.acceptsPlayback()) {
                    Lock lock(app_.mutex);
                    app_.playback.end();
                    if (const auto dropped = app_.playback.droppedFrames()) {
                        ESP_LOGW(tag, "playback_frames_dropped=%u", static_cast<unsigned>(dropped));
                    }
                }
                break;
            case Type::Ping: send({Type::Pong, {{"t", message->integer("t").value_or(0)}}}); break;
            case Type::Pong: break;
            case Type::Unknown: ESP_LOGI(tag, "unknown_message"); break;
            default: badMessage(); break;
        }
    }

    void resetPlayback() {
        app_.playback.clear();
        ++app_.playbackEpoch;
        app_.playbackDrained = false;
        app_.level = {};
    }

    void publish(const Effects& effects) {
        if (effects.stopCapture) {
            app_.capturing = false;
            ++app_.captureEpoch;
        }
        if (effects.startCapture) {
            ++app_.captureEpoch;
            app_.capturing = true;
        }
        if (effects.dropPlayback) resetPlayback();
        if (effects.blink) app_.face.triggerBlink(nowMs());
        app_.state = avatar_.state();
        app_.canPlay = avatar_.canPlay();
    }

    void apply(const Effects& effects) {
        // Publish stop/cancel immediately. Start capture after listen_start is sent.
        if (effects.startCapture) send({Type::ListenStart, {{"session", avatar_.sessionNumber()}}});
        {
            Lock lock(app_.mutex);
            if (effects.startCapture && ioFailed_) return;
            publish(effects);
        }
        if (effects.send == Command::ListenStop) send({Type::ListenStop, {}});
        if (effects.send == Command::Cancel) send({Type::Cancel, {{"session", avatar_.sessionNumber()}}});
    }

    void capture() {
        Captured frame;
        for (int i = 0; !ioFailed_ && i < 4 && xQueueReceive(app_.captured, &frame, 0) == pdTRUE; ++i) {
            bool current;
            {
                Lock lock(app_.mutex);
                current = app_.capturing && frame.epoch == app_.captureEpoch;
            }
            if (current) {
                if (!socket_.sendAudio(frame.pcm)) {
                    ioFailed_ = true;
                    return;
                }
                const auto now = nowMs();
                apply(avatar_.recorded(now, rms(frame.pcm)));
            }
        }
    }

    bool pollPlayback() {
        Lock lock(app_.mutex);
        if (app_.playbackDrained && avatar_.canPlay()) {
            avatar_.drained(nowMs());
            resetPlayback();
            publish({});
        }
        const auto fault = app_.audioFault;
        app_.audioFault = false;
        return fault;
    }

    App& app_;
    Socket socket_;
    Config config_;
    SeededRandom rng_;
    WifiEvents wifiEvents_;
    unsigned wifiStatus_ = 0;
    Millis wifiNext_ = 0;
    Backoff wifiBackoff_;
    LinkSupervisor link_;
    AvatarStateMachine avatar_;
    std::uint32_t reportedDroppedAudio_ = 0;
    bool ioFailed_ = false;
};
}

void netTask(void* context) {
    const auto controls = xQueueCreate(32, sizeof(SocketEvent));
    const auto audio = xQueueCreate(32, sizeof(SocketEvent));
    Network network(*static_cast<App*>(context), controls, audio, readConfig());
    network.run(controls != nullptr && audio != nullptr);
}
}
