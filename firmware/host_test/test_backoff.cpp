#include "gw_test.hpp"
#include <initializer_list>
#include "grokwatch/backoff.hpp"
using namespace grokwatch;

TEST(backoff_sequence_no_jitter) {
    Backoff backoff;
    for (int expected : {1000, 2000, 4000, 8000, 16000, 30000, 30000})
        CHECK_EQ(backoff.next(.5), expected);
}

TEST(backoff_jitter_bounds) {
    SeededRandom rng(42);
    for (int i = 0; i < 10000; ++i) {
        Backoff backoff;
        for (int nominal : {1000, 2000, 4000, 8000, 16000, 30000, 30000}) {
            const auto delay = backoff.next(rng.unit());
            CHECK(delay >= nominal * 8 / 10 && delay <= nominal * 12 / 10);
            CHECK(delay >= 800 && delay <= 30000);
        }
    }
}

TEST(backoff_resets_after_success) {
    Backoff backoff;
    CHECK_EQ(backoff.next(.5), 1000);
    CHECK_EQ(backoff.next(.5), 2000);
    backoff.reset();
    CHECK_EQ(backoff.next(.5), 1000);
}
