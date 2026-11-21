#pragma once
#include "grokwatch/audio_level.hpp"
#include "grokwatch/clock.hpp"
#include <optional>

namespace grokwatch {

enum class State { Disconnected, Idle, Listening, Thinking, Speaking, Error };
enum class Command { None, ListenStart, ListenStop, Cancel };

struct Effects {
    Command send = Command::None;
    bool startCapture = false;
    bool stopCapture = false;
    bool dropPlayback = false;
    bool blink = false;
};

class AvatarStateMachine {
public:
    State state() const { return state_; }
    bool acceptsPlayback() const { return playback_; }
    bool canPlay() const { return playback_ && state_ == State::Speaking; }
    Effects hello(Millis now);
    Effects linkDown(Millis now);
    Effects longPress(Millis now);
    Effects remote(State state, Millis now);
    Effects error(bool noSpeech, bool retryable, Millis now);
    Effects recorded(Millis now, double rms);
    Effects ttsStart(Millis now);
    Effects drained(Millis now);
    Effects tick(Millis now);

private:
    void enter(State state, Millis now);
    void clearPlayback();
    Effects stopListening(Millis now);
    Effects enterError(Millis now);

    State state_ = State::Disconnected;
    Millis entered_ = 0;
    Vad vad_;
    unsigned capturedFrames_ = 0;
    bool playback_ = false;
    bool speakingAnnounced_ = false;
    bool cancelled_ = false;
    std::optional<Millis> deferredIdle_;
};

}
