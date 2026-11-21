#include "grokwatch/avatar_state.hpp"

namespace grokwatch {
namespace {

Effects send(Command command) {
    Effects effects;
    effects.send = command;
    return effects;
}

}

void AvatarStateMachine::enter(State state, Millis now) {
    if (state_ == state) return;
    state_ = state;
    entered_ = now;
}

void AvatarStateMachine::clearPlayback() {
    playback_ = false;
    speakingAnnounced_ = false;
    deferredIdle_.reset();
}

Effects AvatarStateMachine::hello(Millis now) {
    if (state_ == State::Disconnected) {
        cancelled_ = false;
        enter(State::Idle, now);
    }
    return {};
}

Effects AvatarStateMachine::linkDown(Millis now) {
    enter(State::Disconnected, now);
    clearPlayback();
    cancelled_ = false;
    Effects effects;
    effects.stopCapture = effects.dropPlayback = true;
    return effects;
}

Effects AvatarStateMachine::stopListening(Millis now) {
    enter(State::Thinking, now);
    auto effects = send(Command::ListenStop);
    effects.stopCapture = true;
    return effects;
}

Effects AvatarStateMachine::longPress(Millis now) {
    switch (state_) {
        case State::Disconnected: {
            Effects effects;
            effects.blink = true;
            return effects;
        }
        case State::Idle: {
            vad_ = {};
            capturedFrames_ = 0;
            cancelled_ = false;
            enter(State::Listening, now);
            auto effects = send(Command::ListenStart);
            effects.startCapture = true;
            return effects;
        }
        case State::Listening:
            return stopListening(now);
        case State::Thinking:
        case State::Speaking: {
            const bool drop = state_ == State::Speaking;
            clearPlayback();
            cancelled_ = true;
            enter(State::Idle, now);
            auto effects = send(Command::Cancel);
            effects.dropPlayback = drop;
            return effects;
        }
        case State::Error:
            return {};
    }
    return {};
}

Effects AvatarStateMachine::remote(State state, Millis now) {
    if (state_ == State::Disconnected || state == State::Disconnected) return {};
    if (cancelled_ && state != State::Idle) return {};
    if (state == State::Error) return enterError(now);
    if (state == State::Idle && (playback_ || speakingAnnounced_ || state_ == State::Error)) {
        if (!deferredIdle_) deferredIdle_ = now;
        return {};
    }
    if (state == State::Speaking) {
        speakingAnnounced_ = true;
        // Playback starts only after the corresponding tts_start arrives.
        return {};
    }
    if (state_ == State::Error) return {};
    // An acknowledgement of listen_start can arrive after a local stop.
    if (state == State::Listening && state_ != State::Listening) return {};
    Effects effects;
    effects.stopCapture = state_ == State::Listening && state != State::Listening;
    enter(state, now);
    return effects;
}

Effects AvatarStateMachine::enterError(Millis now) {
    enter(State::Error, now);
    Effects effects;
    effects.stopCapture = true;
    return effects;
}

Effects AvatarStateMachine::error(bool noSpeech, bool retryable, Millis now) {
    if (state_ == State::Disconnected || cancelled_) return {};
    if (noSpeech) {
        bool drop = playback_;
        clearPlayback();
        enter(State::Idle, now);
        Effects effects;
        effects.blink = effects.stopCapture = true;
        effects.dropPlayback = drop;
        return effects;
    }
    return retryable ? enterError(now) : Effects{};
}

Effects AvatarStateMachine::recorded(Millis now, double amplitude) {
    if (state_ != State::Listening) return {};
    ++capturedFrames_;
    if (vad_.frame(amplitude) || capturedFrames_ >= 750) return stopListening(now);
    return tick(now);
}

Effects AvatarStateMachine::ttsStart(Millis now) {
    const bool announcedAfterError = state_ == State::Idle && speakingAnnounced_;
    if (cancelled_ || (!announcedAfterError && state_ != State::Thinking &&
        state_ != State::Speaking && state_ != State::Error)) return {};
    playback_ = true;
    speakingAnnounced_ = false;
    if (state_ != State::Error) enter(State::Speaking, now);
    return {};
}

Effects AvatarStateMachine::drained(Millis now) {
    if (!canPlay()) return {};
    clearPlayback();
    enter(State::Idle, now);
    return {};
}

Effects AvatarStateMachine::tick(Millis now) {
    if (state_ == State::Listening &&
        (now - entered_ >= 15000 || (!vad_.heardSpeech() && now - entered_ >= 5000))) {
        return stopListening(now);
    }
    if (state_ == State::Thinking && now - entered_ >= 100000) {
        const bool drop = playback_;
        clearPlayback();
        cancelled_ = true;
        enter(State::Error, now);
        auto effects = send(Command::Cancel);
        effects.dropPlayback = drop;
        return effects;
    }
    if (state_ == State::Error && now - entered_ < 1500) return {};
    if (deferredIdle_ && now - *deferredIdle_ >= 2000) {
        clearPlayback();
        enter(State::Idle, now);
        Effects effects;
        effects.dropPlayback = true;
        return effects;
    }
    if (state_ == State::Error) {
        if (playback_) {
            enter(State::Speaking, now);
        } else if (!speakingAnnounced_) {
            clearPlayback();
            enter(State::Idle, now);
        } else {
            // A speaking announcement is immediately followed by tts_start.
            enter(State::Speaking, now);
        }
    }
    return {};
}

}
