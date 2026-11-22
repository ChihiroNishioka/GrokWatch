#pragma once
#include <cstdint>
#include <random>

namespace grokwatch {

class Random {
public:
    virtual ~Random() = default;
    virtual double unit() = 0;
};

class SeededRandom final : public Random {
public:
    explicit SeededRandom(std::uint32_t seed) : engine_(seed) {}
    double unit() override {
        return static_cast<double>(engine_() - engine_.min()) /
               (static_cast<double>(engine_.max()) - engine_.min() + 1.0);
    }

private:
    std::mt19937 engine_;
};

}
