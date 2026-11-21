#include "gw_test.hpp"
#include "grokwatch/volume.hpp"

#include <array>

using namespace grokwatch;

namespace {
int sample(VolumeKeys& keys, Millis now, bool up, bool down, int& level) {
    level = keys.sample(now, up, down, level);
    return level;
}

int beginUp(VolumeKeys& keys, int& level, Millis start = 0) {
    sample(keys, start, false, false, level);
    sample(keys, start + 10, true, false, level);
    sample(keys, start + 20, true, false, level);
    return sample(keys, start + 30, true, false, level);
}
}

TEST(keys_debounce_10ms) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    sample(keys, 0, false, false, level);
    const bool noise[] = {true, false, true, false};
    for (int i = 0; i < 4; ++i)
        sample(keys, 10 + i * 10, noise[i], false, level);
    CHECK_EQ(level, defaultVolumeLevel);
    sample(keys, 50, true, false, level);
    sample(keys, 60, true, false, level);
    sample(keys, 70, true, false, level);
    CHECK_EQ(level, defaultVolumeLevel + 1);
}

TEST(keys_short_glitch_ignored) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    sample(keys, 0, false, false, level);
    sample(keys, 10, true, false, level);
    sample(keys, 20, true, false, level);
    sample(keys, 30, false, false, level);
    sample(keys, 40, false, false, level);
    CHECK_EQ(level, defaultVolumeLevel);
}

TEST(keys_held_at_start_ignored) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    sample(keys, 0, true, false, level);
    sample(keys, 10, true, false, level);
    sample(keys, 20, true, false, level);
    sample(keys, 4000, true, false, level);
    CHECK_EQ(level, defaultVolumeLevel);
    sample(keys, 4010, false, false, level);
    sample(keys, 4020, false, false, level);
    sample(keys, 4030, false, false, level);
    CHECK_EQ(sample(keys, 4060, true, false, level), defaultVolumeLevel);
    sample(keys, 4070, true, false, level);
    CHECK_EQ(sample(keys, 4080, true, false, level), defaultVolumeLevel + 1);
}

TEST(keys_release_glitch_keeps_repeat) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    beginUp(keys, level);
    sample(keys, 100, false, false, level);
    sample(keys, 110, false, false, level);
    sample(keys, 120, true, false, level);
    for (Millis time = 130; time < 430; time += 10)
        sample(keys, time, true, false, level);
    sample(keys, 430, true, false, level);
    CHECK_EQ(level, defaultVolumeLevel + 2);
}

TEST(keys_single_press_one_level) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    beginUp(keys, level);
    sample(keys, 400, false, false, level);
    sample(keys, 410, false, false, level);
    sample(keys, 420, false, false, level);
    CHECK_EQ(level, defaultVolumeLevel + 1);

    VolumeKeys atDeadline;
    int deadlineLevel = defaultVolumeLevel;
    beginUp(atDeadline, deadlineLevel);
    sample(atDeadline, 410, false, false, deadlineLevel);
    sample(atDeadline, 420, false, false, deadlineLevel);
    sample(atDeadline, 430, false, false, deadlineLevel);
    CHECK_EQ(deadlineLevel, defaultVolumeLevel + 2);
}

TEST(keys_hold_accelerates) {
    VolumeKeys keys;
    int level = 0;
    sample(keys, 0, false, false, level);
    const std::array<Millis, 10> expected{{30, 430, 630, 790, 920, 1020, 1100, 1160, 1210, 1260}};
    Millis changedAt[expected.size()]{};
    std::size_t changed = 0;
    for (Millis time = 10; time <= expected.back(); time += 10) {
        const int before = level;
        sample(keys, time, true, false, level);
        if (level != before) changedAt[changed++] = time;
    }
    CHECK_EQ(changed, expected.size());
    for (std::size_t i = 0; i < expected.size(); ++i) CHECK_EQ(changedAt[i], expected[i]);
}

TEST(keys_hold_rate_cap) {
    VolumeKeys keys;
    int level = 0;
    sample(keys, 0, false, false, level);
    Millis previous = -1;
    for (Millis time = 10; time <= 2000; time += 10) {
        const int before = level;
        sample(keys, time, true, false, level);
        if (level != before) {
            if (previous >= 0 && level >= 8) CHECK(time - previous >= 50);
            previous = time;
        }
    }
}

TEST(keys_full_sweep_time) {
    VolumeKeys up;
    int high = 0;
    sample(up, 0, false, false, high);
    for (Millis time = 10; time <= 3310; time += 10) sample(up, time, true, false, high);
    CHECK_EQ(high, volumeSteps);

    VolumeKeys fromDefaultUp;
    high = defaultVolumeLevel;
    sample(fromDefaultUp, 0, false, false, high);
    for (Millis time = 10; time <= 2010; time += 10) sample(fromDefaultUp, time, true, false, high);
    CHECK_EQ(high, volumeSteps);

    VolumeKeys down;
    int low = defaultVolumeLevel;
    sample(down, 0, false, false, low);
    for (Millis time = 10; time <= 2060; time += 10) sample(down, time, false, true, low);
    CHECK_EQ(low, 0);
}

TEST(keys_stop_at_ends) {
    VolumeKeys up;
    int high = volumeSteps - 1;
    sample(up, 0, false, false, high);
    for (Millis time = 10; time <= 1000; time += 10) sample(up, time, true, false, high);
    CHECK_EQ(high, volumeSteps);
    for (Millis time = 1010; time <= 11000; time += 10) sample(up, time, true, false, high);
    CHECK_EQ(high, volumeSteps);
    for (Millis time = 11010; time <= 11030; time += 10) sample(up, time, false, false, high);
    for (Millis time = 11040; time <= 11060; time += 10) sample(up, time, false, true, high);
    CHECK_EQ(high, volumeSteps - 1);

    VolumeKeys down;
    int low = 1;
    sample(down, 0, false, false, low);
    for (Millis time = 10; time <= 1000; time += 10) sample(down, time, false, true, low);
    CHECK_EQ(low, 0);
    for (Millis time = 1010; time <= 11000; time += 10) sample(down, time, false, true, low);
    CHECK_EQ(low, 0);
    for (Millis time = 11010; time <= 11030; time += 10) sample(down, time, false, false, low);
    for (Millis time = 11040; time <= 11060; time += 10) sample(down, time, true, false, low);
    CHECK_EQ(low, 1);
}

TEST(keys_late_sample_moves_one) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    beginUp(keys, level);
    CHECK_EQ(sample(keys, 530, true, false, level), defaultVolumeLevel + 2);
    CHECK_EQ(sample(keys, 540, true, false, level), defaultVolumeLevel + 2);
}

TEST(keys_both_pressed_ignored) {
    VolumeKeys simultaneous;
    int level = defaultVolumeLevel;
    sample(simultaneous, 0, false, false, level);
    for (Millis time = 10; time <= 1000; time += 10)
        sample(simultaneous, time, true, true, level);
    CHECK_EQ(level, defaultVolumeLevel);

    VolumeKeys secondKey;
    level = defaultVolumeLevel;
    beginUp(secondKey, level);
    sample(secondKey, 40, true, true, level);
    sample(secondKey, 50, true, true, level);
    sample(secondKey, 60, true, true, level);
    for (Millis time = 70; time <= 1000; time += 10)
        sample(secondKey, time, true, true, level);
    CHECK_EQ(level, defaultVolumeLevel + 1);
    for (Millis time = 1010; time <= 1030; time += 10)
        sample(secondKey, time, false, false, level);
    for (Millis time = 1040; time <= 1060; time += 10)
        sample(secondKey, time, false, true, level);
    CHECK_EQ(level, defaultVolumeLevel);
}

TEST(keys_value_updates_immediately) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    CHECK_EQ(beginUp(keys, level), defaultVolumeLevel + 1);
}

TEST(keys_log_once_per_press) {
    VolumeKeys keys;
    int level = defaultVolumeLevel;
    beginUp(keys, level);
    CHECK(!keys.takeLogRequest());
    sample(keys, 40, false, false, level);
    sample(keys, 50, false, false, level);
    sample(keys, 60, false, false, level);
    CHECK(keys.takeLogRequest());
    CHECK(!keys.takeLogRequest());

    VolumeKeys both;
    level = defaultVolumeLevel;
    beginUp(both, level);
    sample(both, 40, true, true, level);
    sample(both, 50, true, true, level);
    sample(both, 60, true, true, level);
    CHECK(both.takeLogRequest());
    CHECK(!both.takeLogRequest());

    VolumeKeys unchanged;
    level = volumeSteps;
    sample(unchanged, 0, false, false, level);
    sample(unchanged, 10, true, false, level);
    sample(unchanged, 20, true, false, level);
    sample(unchanged, 30, true, false, level);
    sample(unchanged, 40, false, false, level);
    sample(unchanged, 50, false, false, level);
    sample(unchanged, 60, false, false, level);
    CHECK(!unchanged.takeLogRequest());
}
