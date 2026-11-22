#pragma once
#include "grokwatch/backoff.hpp"

namespace grokwatch {

enum class LinkAction { None, Connect, Hello, Ready, Ping, Disconnect };

class LinkSupervisor {
public:
    LinkAction wifi(bool available, Millis now);
    LinkAction opened(Millis now);
    LinkAction authenticated(Millis now);
    LinkAction reject(Millis now);
    LinkAction failed(Millis now, double jitter);
    void received(Millis now);
    LinkAction tick(Millis now, double jitter);
    bool ready() const { return phase_ == Phase::Ready; }

private:
    enum class Phase { Waiting, Connecting, AwaitHello, Ready };
    Phase phase_ = Phase::Waiting;
    bool wifi_ = false;
    bool authRejected_ = false;
    Millis nextConnect_ = 0;
    Millis deadline_ = 0;
    Millis nextPing_ = 0;
    Backoff backoff_;
};

}
