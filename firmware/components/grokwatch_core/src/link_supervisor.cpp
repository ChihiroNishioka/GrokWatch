#include "grokwatch/link_supervisor.hpp"

namespace grokwatch {

LinkAction LinkSupervisor::wifi(bool available, Millis now) {
    if (wifi_ == available) return LinkAction::None;
    wifi_ = available;
    if (available) return LinkAction::None;
    const bool disconnect = phase_ != Phase::Waiting;
    phase_ = Phase::Waiting;
    if (disconnect) nextConnect_ = now + (authRejected_ ? 30000 : 0);
    return disconnect ? LinkAction::Disconnect : LinkAction::None;
}

LinkAction LinkSupervisor::opened(Millis now) {
    if (phase_ != Phase::Connecting) return LinkAction::None;
    phase_ = Phase::AwaitHello;
    deadline_ = now + 5000;
    return LinkAction::Hello;
}

LinkAction LinkSupervisor::authenticated(Millis now) {
    if (phase_ != Phase::AwaitHello) return LinkAction::None;
    phase_ = Phase::Ready;
    authRejected_ = false;
    backoff_.reset();
    received(now);
    nextPing_ = now + 10000;
    return LinkAction::Ready;
}

LinkAction LinkSupervisor::reject(Millis now) {
    if (phase_ != Phase::AwaitHello) return LinkAction::None;
    authRejected_ = true;
    return failed(now, 0.5);
}

LinkAction LinkSupervisor::failed(Millis now, double jitter) {
    if (phase_ == Phase::Waiting) return LinkAction::None;
    phase_ = Phase::Waiting;
    nextConnect_ = now + (authRejected_ ? 30000 : backoff_.next(jitter));
    return LinkAction::Disconnect;
}

void LinkSupervisor::received(Millis now) {
    if (ready()) deadline_ = now + 25000;
}

LinkAction LinkSupervisor::tick(Millis now, double jitter) {
    if (!wifi_) return LinkAction::None;
    if (phase_ == Phase::Waiting) {
        if (now < nextConnect_) return LinkAction::None;
        phase_ = Phase::Connecting;
        deadline_ = now + 5000;
        return LinkAction::Connect;
    }
    if (now >= deadline_) return failed(now, jitter);
    if (ready() && now >= nextPing_) {
        nextPing_ = now + 10000;
        return LinkAction::Ping;
    }
    return LinkAction::None;
}

}
