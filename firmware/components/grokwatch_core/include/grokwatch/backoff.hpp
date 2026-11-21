#pragma once
#include "grokwatch/clock.hpp"
#include "grokwatch/rng.hpp"
#include <algorithm>
#include <cmath>

namespace grokwatch {

class Backoff {
public:
    Millis next(double unit) {
        const auto delay = std::lround(nominal_ * (0.8 + 0.4 * std::clamp(unit, 0.0, 1.0)));
        nominal_ = std::min<Millis>(nominal_ * 2, 30000);
        return std::clamp<Millis>(delay, 800, 30000);
    }

    void reset() { nominal_ = 1000; }

private:
    Millis nominal_ = 1000;
};

}
