#pragma once

#include "grokwatch/gaze.hpp"
#include "grokwatch/rng.hpp"

namespace grokwatch {

struct DriftSample {
    Vec gaze;
    Vec target;
    bool newTarget;
};

class Drift {
public:
    DriftSample update(Millis now, Random& rng);

private:
    bool started_ = false;
    Millis start_ = 0;
    Millis end_ = 0;
    Vec origin_;
    Vec target_;
};

Vec thinkingGaze(Millis elapsed);

}  // namespace grokwatch
