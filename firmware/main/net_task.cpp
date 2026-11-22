#include "app.hpp"
#include "config_store.hpp"
#include "grokwatch/link_supervisor.hpp"
#include "grokwatch/protocol.hpp"
#include "grokwatch/socket_event_queue.hpp"

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

void wifiEvent(void* context, esp_event_base_t base, int32_t id, void* data) {
    auto& status = static_cast<WifiEvents*>(context)->status;
    const auto old = status.load();
    // Diagnostic status only: never log SSID, password, addresses or tokens.
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        ESP_LOGI(tag, "diag wifi: associated");
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED && data) {
        ESP_LOGI(tag, "diag wifi: disconnected reason=%d",
                 static_cast<const wifi_event_sta_disconnected_t*>(data)->reason);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGI(tag, "diag wifi: got ip");
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        status.store(old | 1u);
    } else if ((base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) ||
               (base == IP_EVENT && id == IP_EVENT_STA_LOST_IP)) {
        status.store((old & ~1u) + 2u);
    }
}

// Diagnostic scan: reports only counts, channel, auth mode and signal of the target.
void diagScan(const Config& config) {
    if (esp_wifi_scan_start(nullptr, true) != ESP_OK) {
        ESP_LOGI(tag, "diag scan: failed");
        return;
    }
    uint16_t count = 20;
    // diagScan is called only by netTask, so this buffer has one writer.
    static std::array<wifi_ap_record_t, 20> aps{};
    if (esp_wifi_scan_get_ap_records(&count, aps.data()) != ESP_OK) count = 0;
    int nonAscii = 0;
    bool found = false;
    for (uint16_t i = 0; i < count; ++i) {
        const auto* ssid = reinterpret_cast<const char*>(aps[i].ssid);
        const auto len = strnlen(ssid, sizeof(aps[i].ssid));
        bool wide = false;
        for (std::size_t k = 0; k < len; ++k) wide |= static_cast<unsigned char>(ssid[k]) > 0x7f;
        if (wide) {
            ++nonAscii;
            ESP_LOGI(tag, "diag scan: non-ascii ap ch=%u", aps[i].primary);
        }
        if (len == config.ssid.size() && std::memcmp(ssid, config.ssid.data(), len) == 0) {
            found = true;
            ESP_LOGI(tag, "diag scan: target found ch=%u auth=%d rssi=%d", aps[i].primary,
                     static_cast<int>(aps[i].authmode), aps[i].rssi);
        }
    }
    ESP_LOGI(tag, "diag scan: aps=%u non_ascii=%d target_found=%d", count, nonAscii, found ? 1 : 0);
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
           esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_CONNECTED, wifiEvent, &events) == ESP_OK &&
           esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, wifiEvent, &events) == ESP_OK &&
           esp_wifi_set_storage(WIFI_STORAGE_RAM) == ESP_OK &&
           esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK &&
           esp_wifi_set_config(WIFI_IF_STA, &sta) == ESP_OK && esp_wifi_start() == ESP_OK &&
           (diagScan(config), true);
}

class Socket {
public:
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
        ESP_LOGI(tag, "diag ws: connecting");
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
        portENTER_CRITICAL(&eventsMux_);
        const bool received = events_.receive(event);
        portEXIT_CRITICAL(&eventsMux_);
        return received;
    }

    bool overflow() const { return overflow_.load(); }
    std::uint32_t droppedAudio() const {
        portENTER_CRITICAL(&eventsMux_);
        const auto dropped = events_.droppedAudio();
        portEXIT_CRITICAL(&eventsMux_);
        return dropped;
    }

private:
    static void onEvent(void* context, esp_event_base_t, int32_t id, void* data) {
        auto& socket = *static_cast<Socket*>(context);
        switch (id) {
            case WEBSOCKET_EVENT_CONNECTED:
                ESP_LOGI(tag, "diag ws: connected");
                socket.post({SocketEventKind::Open});
                break;
            case WEBSOCKET_EVENT_ERROR: ESP_LOGI(tag, "diag ws: error"); break;
            case WEBSOCKET_EVENT_DISCONNECTED:
                ESP_LOGI(tag, "diag ws: disconnected");
                socket.post({SocketEventKind::Closed});
                break;
            case WEBSOCKET_EVENT_CLOSED:
            case WEBSOCKET_EVENT_FINISH: socket.post({SocketEventKind::Closed}); break;
            case WEBSOCKET_EVENT_DATA:
                socket.fragment(*static_cast<const esp_websocket_event_data_t*>(data));
                break;
            default: break;
        }
    }

    void post(SocketEvent event) {
        portENTER_CRITICAL(&eventsMux_);
        const auto result = events_.post(event);
        portEXIT_CRITICAL(&eventsMux_);
        if (result != QueuePost::Accepted) {
            delete[] event.data;
            if (result == QueuePost::Overflow) overflow_.store(true);
        }
    }

    void fragment(const esp_websocket_event_data_t& frame) {
        constexpr int text = 1;
        constexpr int binary = 2;
        if (frame.op_code >= 8) {
            post({SocketEventKind::Activity});
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
            post({opcode_ == text ? SocketEventKind::BadText : SocketEventKind::Activity});
        } else {
            auto data = new (std::nothrow) char[used_ ? used_ : 1];
            if (data) {
                std::memcpy(data, buffer_.data(), used_);
                post({opcode_ == text ? SocketEventKind::Text : SocketEventKind::Audio, data, used_});
            } else {
                overflow_.store(true);
            }
        }
        opcode_ = 0;
    }

    SocketEventQueue events_;
    mutable portMUX_TYPE eventsMux_ = portMUX_INITIALIZER_UNLOCKED;
    esp_websocket_client_handle_t handle_ = nullptr;
    std::atomic<bool> overflow_{false};
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
    Network(App& app, Config config)
        : app_(app), config_(std::move(config)), rng_(esp_random()) {}

    void run() {
        const bool configured = config_.ready();
        const bool wifiStarted = configured && startWifi(config_, wifiEvents_);
        if (!configured) ESP_LOGI(tag, "設定なし");
        else if (!wifiStarted) ESP_LOGE(tag, "network_init_failed");

        auto nextStackReport = nowMs();
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
            now = nowMs();
            if (now >= nextStackReport) {
                ESP_LOGI(tag, "diag stack free net=%u audio=%u render=%u buttons=%u touch=%u",
                         static_cast<unsigned>(uxTaskGetStackHighWaterMark(app_.netTaskHandle)),
                         static_cast<unsigned>(uxTaskGetStackHighWaterMark(app_.audioTaskHandle)),
                         static_cast<unsigned>(uxTaskGetStackHighWaterMark(app_.renderTaskHandle)),
                         static_cast<unsigned>(uxTaskGetStackHighWaterMark(app_.buttonTaskHandle)),
                         static_cast<unsigned>(uxTaskGetStackHighWaterMark(app_.touchTaskHandle)));
                nextStackReport = now + 60000;
            }
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
                case SocketEventKind::Open:
                    linkAction(link_.opened(now), now);
                    break;
                case SocketEventKind::Closed: linkAction(link_.failed(now, rng_.unit()), now); break;
                case SocketEventKind::BadText:
                    link_.received(now);
                    badMessage();
                    break;
                case SocketEventKind::Activity: link_.received(now); break;
                case SocketEventKind::Text:
                    link_.received(now);
                    receiveText({data.get(), event.size}, now);
                    break;
                case SocketEventKind::Audio:
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
        if (action == LinkAction::Connect && !socket_.open(config_)) {
            action = link_.failed(now, rng_.unit());
        }
        switch (action) {
            case LinkAction::None: break;
            case LinkAction::Connect: break;
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
    static Network network(*static_cast<App*>(context), readConfig());
    network.run();
}
}
