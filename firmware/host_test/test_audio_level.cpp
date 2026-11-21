#include "gw_test.hpp"
#include "grokwatch/audio_level.hpp"
using namespace grokwatch;

TEST(audio_level_mapping_and_smoothing) {
    CHECK_EQ(rawLevel(0), 0);
    CHECK_EQ(rawLevel(3000), .5);
    CHECK_EQ(rawLevel(6000), 1);
    CHECK_EQ(rawLevel(7000), 1);
    AudioLevel level;
    level.frame(20, 6000);
    const auto up = 1 - std::exp(-20.0 / 30);
    CHECK_NEAR(level.value(20), up, 1e-6);
    level.frame(40, 0);
    CHECK_NEAR(level.value(40), up * std::exp(-20.0 / 120), 1e-6);
}

TEST(audio_level_decays_when_audio_stops) {
    AudioLevel level;
    level.frame(20, 6000);
    const auto initial = level.value(20);
    CHECK_EQ(level.value(120), initial);
    CHECK(level.value(220) > 0 && level.value(220) < initial);
    CHECK_EQ(level.value(320), 0);
}

TEST(vad_thresholds) {
    Vad vad;
    for (int frame = 0; frame < 70; ++frame) CHECK(!vad.frame(499));
    CHECK(!vad.heardSpeech());
    CHECK(!vad.frame(500));
    CHECK(vad.heardSpeech());
    for (int frame = 0; frame < 59; ++frame) CHECK(!vad.frame(499));
    CHECK(vad.frame(499));
}

TEST(playback_buffer_threshold_and_short_reply) {
    PlaybackBuffer buffer;
    PcmFrame sample{};
    sample[0] = 42;
    buffer.start();
    for (int i = 0; i < 14; ++i) CHECK(buffer.push(sample));
    PcmFrame out{};
    CHECK(!buffer.pop(out));
    CHECK(buffer.push(sample));
    CHECK(buffer.pop(out));
    CHECK_EQ(out[0], 42);
    buffer.clear();
    buffer.start();
    CHECK(buffer.push(sample));
    CHECK(!buffer.pop(out));
    buffer.end();
    CHECK(buffer.pop(out));
    CHECK(buffer.complete());
    buffer.start();
    buffer.end();
    CHECK(buffer.complete());
}

TEST(playback_buffer_discards_oldest_when_full) {
    PlaybackBuffer buffer;
    buffer.start();
    PcmFrame frame{};
    for (int i = 0; i < 98; ++i) {
        frame[0] = i;
        CHECK(buffer.push(frame));
    }
    CHECK_EQ(buffer.droppedFrames(), 2u);
    for (int i = 2; i < 98; ++i) {
        CHECK(buffer.pop(frame));
        CHECK_EQ(frame[0], i);
    }
    CHECK(!buffer.pop(frame));
}
