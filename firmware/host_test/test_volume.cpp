#include "gw_test.hpp"
#include "grokwatch/volume.hpp"

#include <cmath>

using namespace grokwatch;

TEST(volume_levels_match_spec) {
    CHECK_EQ(volumeLevelCount, 52);
    CHECK_EQ(defaultVolumeLevel, 26);
    for (int level = 0; level <= volumeSteps; ++level) {
        const VolumeControl volume(level);
        CHECK_EQ(volume.level(), level);
        CHECK_EQ(volume.value(), level * 5);
    }
    CHECK_EQ(VolumeControl().value(), 130);
}

TEST(volume_gain_matches_table) {
    const int selected[] = {1, 2, 4, 5, 10, 13, 26, 39, 50, 51};
    const double expected[] = {-68.4, -56.4, -44.4, -40.5, -28.4,
                               -23.9, -11.8, -4.8, -0.48, -0.14};
    for (std::size_t i = 0; i < std::size(selected); ++i) {
        const auto value = static_cast<std::uint8_t>(selected[i] * 5);
        const double db = 20 * std::log10(speakerGain(8, true, value, 255));
        CHECK_NEAR(db, expected[i], 0.05);
    }
    for (int level = 1; level <= volumeSteps; ++level) {
        const auto value = static_cast<std::uint8_t>(level * 5);
        const double db = 20 * std::log10(speakerGain(8, true, value, 255));
        CHECK_NEAR(db, 40 * std::log10(value) - 96.40, 0.05);
    }
}

TEST(volume_zero_is_silent) {
    CHECK_EQ(speakerGain(8, true, 0, 255), 0.0);
}

TEST(volume_gain_never_clips) {
    CHECK(speakerGain(8, true, 255, 255) <= 1.0);
    CHECK(32767 * speakerGain(8, true, 255, 255) <= 32767);
}

TEST(volume_current_default_is_minus_42db) {
    CHECK_NEAR(20 * std::log10(speakerGain(1, true, 64, 255)), -42.2, 0.1);
}

TEST(volume_step_one_level) {
    VolumeControl volume;
    CHECK(volume.step(1));
    CHECK_EQ(volume.level(), 27);
    CHECK_EQ(volume.value(), 135);
    CHECK(volume.step(-1));
    CHECK_EQ(volume.level(), defaultVolumeLevel);
    CHECK(!volume.step(0));
}

TEST(volume_step_stops_at_ends) {
    VolumeControl low(0);
    VolumeControl high(volumeSteps);
    CHECK(!low.step(-1));
    CHECK(!high.step(1));
    CHECK_EQ(low.value(), 0);
    CHECK_EQ(high.value(), 255);
    CHECK(low.step(1));
    CHECK(high.step(-1));
}
