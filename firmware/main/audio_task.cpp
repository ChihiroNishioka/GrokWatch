#include "app.hpp"
#include "grokwatch/volume.hpp"

#include <M5Unified.h>
#include <array>
#include <optional>

namespace gwapp {
namespace {

using grokwatch::Millis;
using grokwatch::PcmFrame;
using grokwatch::sampleRate;

void captureFault(App& app, unsigned epoch) {
    Lock lock(app.mutex);
    if ((app.capturing || app.wakeListening) && app.captureEpoch == epoch) app.audioFault = true;
}

class Capture {
public:
    // Keep the microphone exclusive until its in-flight recording has finished.
    bool pump(App& app, bool requested, unsigned epoch) {
        const auto queued = M5.Mic.isRecording();
        if (queued != 0) acknowledged_ = true;
        if (pending_ != 0 && !acknowledged_) {
            // isRecording() can report zero before the driver takes its first buffer.
            if (nowMs() - submittedAt_ < 100) return true;
            captureFault(app, epoch_);
            M5.Mic.end();
            pending_ = 0;
            failed_ = true;
            disabled_ = true;
        }

        if (!requested || epoch_ != epoch || failed_) {
            if (queued != 0) return true;
            if (M5.Mic.isRunning()) M5.Mic.end();
            pending_ = 0;
            if (!requested) return false;
            if (epoch_ == epoch) return true;
            epoch_ = epoch;
            failed_ = false;
        }
        if (disabled_) {
            failed_ = true;
            captureFault(app, epoch_);
            return true;
        }

        while (pending_ > queued) {
            --pending_;
            const bool sent = xQueueSend(app.captured, &frames_[oldest_], 0) == pdTRUE;
            oldest_ = (oldest_ + 1) % frames_.size();
            if (!sent) {
                failed_ = true;
                captureFault(app, epoch_);
                return true;
            }
        }
        if (pending_ == frames_.size()) return true;

        if (!M5.Mic.isRunning()) {
            M5.Mic.setSampleRate(sampleRate);
            // Settle the driver's sample rate before giving it a buffer.
            if (!M5.Mic.begin()) {
                failed_ = true;
                captureFault(app, epoch_);
                return true;
            }
        }
        auto& next = frames_[(oldest_ + pending_) % frames_.size()];
        next.epoch = epoch_;
        if (!M5.Mic.record(next.pcm.data(), next.pcm.size(), sampleRate)) {
            failed_ = true;
            captureFault(app, epoch_);
            return true;
        }
        if (pending_++ == 0) {
            submittedAt_ = nowMs();
            acknowledged_ = false;
        }
        return true;
    }

private:
    std::array<Captured, 2> frames_{};
    std::size_t oldest_ = 0;
    std::size_t pending_ = 0;
    unsigned epoch_ = 0;
    Millis submittedAt_ = 0;
    bool acknowledged_ = false;
    bool failed_ = false;
    bool disabled_ = false;
};

class Playback {
public:
    void stop() {
        if (M5.Speaker.isRunning()) M5.Speaker.end();
        next_ = 0;
        emptySince_.reset();
        havePlayed_ = false;
    }

    void pump(App& app, unsigned epoch) {
        if (epoch_ != epoch) {
            stop();
            epoch_ = epoch;
            failed_ = false;
        }
        if (failed_) return;

        const auto queued = M5.Speaker.isPlaying(channel_);
        if (queued >= frames_.size()) return;

        auto& pcm = frames_[next_];
        bool haveFrame;
        bool complete;
        {
            Lock lock(app.mutex);
            if (!current(app)) return;
            haveFrame = app.playback.pop(pcm);
            complete = app.playback.complete();
        }

        if (haveFrame) {
            if (!M5.Speaker.begin()) {
                fault(app);
                return;
            }
            {
                Lock lock(app.mutex);
                if (!current(app)) return;
            }
            if (!M5.Speaker.playRaw(pcm.data(), pcm.size(), sampleRate, false, 1, channel_)) {
                stop();
                fault(app);
                return;
            }
            // With two driver slots, a free slot always releases the oldest buffer.
            next_ = (next_ + 1) % frames_.size();
            emptySince_.reset();
            havePlayed_ = true;
            const auto amplitude = grokwatch::rms(pcm);
            Lock lock(app.mutex);
            if (current(app)) app.level.frame(nowMs(), amplitude);
        } else if (queued == 0) {
            if (!emptySince_) emptySince_ = nowMs();
            if (complete && (!havePlayed_ || nowMs() - *emptySince_ >= dmaTail())) {
                stop();
                Lock lock(app.mutex);
                if (current(app)) app.playbackDrained = true;
            }
        }
    }

private:
    static constexpr uint8_t channel_ = 0;
    std::array<PcmFrame, 2> frames_{};
    std::size_t next_ = 0;
    unsigned epoch_ = 0;
    std::optional<Millis> emptySince_;
    bool havePlayed_ = false;
    bool failed_ = false;

    bool current(const App& app) const {
        return app.playbackEpoch == epoch_ && app.canPlay && !app.capturing;
    }

    void fault(App& app) {
        failed_ = true;
        Lock lock(app.mutex);
        if (current(app)) app.audioFault = true;
    }

    static Millis dmaTail() {
        // isPlaying() counts PCM buffers the mixer still references. Wait for the
        // I2S DMA ring and the mixer's final write to drain before powering off.
        const auto config = M5.Speaker.config();
        const Millis samples = (config.dma_buf_count + 1) * config.dma_buf_len;
        return (samples * 1000 + config.sample_rate - 1) / config.sample_rate;
    }
};

}  // namespace

bool configureAudio() {
    if (!M5.Mic.isEnabled() || !M5.Speaker.isEnabled()) return false;
    auto config = M5.Speaker.config();
    config.magnification = grokwatch::speakerMagnification;
    M5.Speaker.config(config);
    return true;
}

void audioTask(void* context) {
    auto& app = *static_cast<App*>(context);
    // There is one audio task, so it owns these persistent buffers in static storage.
    static Capture capture;
    static Playback playback;
    auto appliedVolume = grokwatch::defaultVolumeValue;
    M5.Speaker.setVolume(appliedVolume);
    for (;;) {
        bool capturing;
        unsigned captureEpoch;
        bool canPlay;
        unsigned playbackEpoch;
        std::uint8_t volume;
        {
            Lock lock(app.mutex);
            capturing = app.capturing || app.wakeListening;
            captureEpoch = app.captureEpoch;
            canPlay = app.canPlay;
            playbackEpoch = app.playbackEpoch;
            volume = app.volume.value();
        }
        if (capturing || !canPlay) playback.stop();
        if (volume != appliedVolume) {
            M5.Speaker.setVolume(volume);
            appliedVolume = volume;
        }
        if (!capture.pump(app, capturing, captureEpoch) && canPlay) {
            playback.pump(app, playbackEpoch);
        }
        vTaskDelay(1);
    }
}

}  // namespace gwapp
