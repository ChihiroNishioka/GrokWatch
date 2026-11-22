#pragma once

#include <optional>

#include "grokwatch/avatar_state.hpp"
#include "grokwatch/rng.hpp"

namespace grokwatch {

struct BlinkSample {
    double scale = 1;
    bool started = false;
};

class Blink {
public:
    void trigger(Millis now, Random& rng);
    BlinkSample update(State state, Millis now, Random& rng);

private:
    std::optional<Millis> startedAt_;
    std::optional<Millis> dueAt_;
    bool reportStart_ = false;
    bool wasAutomatic_ = false;
};

}  // namespace grokwatch
