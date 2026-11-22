#include "gw_test.hpp"
#include "grokwatch/protocol.hpp"
using namespace grokwatch;

TEST(protocol_roundtrip_all_types) {
    struct Case { Message message; const char* json; };
    const Case messages[] = {
        {{Type::Hello, {{"v", 1}, {"token", "example"}, {"fw", "0.1.0"}}}, R"({"type":"hello","v":1,"token":"example","fw":"0.1.0"})"},
        {{Type::HelloOk, {{"v", 1}}}, R"({"type":"hello_ok","v":1})"},
        {{Type::AuthError, {{"code", "bad_token"}}}, R"({"type":"auth_error","code":"bad_token"})"},
        {{Type::ListenStart, {}}, R"({"type":"listen_start"})"},
        {{Type::ListenStop, {}}, R"({"type":"listen_stop"})"},
        {{Type::Cancel, {}}, R"({"type":"cancel"})"},
        {{Type::State, {{"state", "thinking"}}}, R"({"type":"state","state":"thinking"})"},
        {{Type::State, {{"state", "idle"}, {"session", 3}}}, R"({"type":"state","state":"idle","session":3})"},
        {{Type::TtsStart, {{"sample_rate", 16000}}}, R"({"type":"tts_start","sample_rate":16000})"},
        {{Type::TtsStart, {{"sample_rate", 16000}, {"emotion", "happy"}}}, R"({"type":"tts_start","sample_rate":16000,"emotion":"happy"})"},
        {{Type::HelloOk, {{"v", 1}, {"wake", true}}}, R"({"type":"hello_ok","v":1,"wake":true})"},
        {{Type::HelloOk, {{"v", 1}, {"wake", false}}}, R"({"type":"hello_ok","v":1,"wake":false})"},
        {{Type::WakeStart, {{"seq", 1}}}, R"({"type":"wake_start","seq":1})"},
        {{Type::WakeStop, {{"seq", 42}}}, R"({"type":"wake_stop","seq":42})"},
        {{Type::Wake, {{"seq", 7}, {"hit", true}}}, R"({"type":"wake","seq":7,"hit":true})"},
        {{Type::Wake, {{"seq", 7}, {"hit", false}}}, R"({"type":"wake","seq":7,"hit":false})"},
        {{Type::TtsEnd, {}}, R"({"type":"tts_end"})"},
        {{Type::Error, {{"code", "internal"}, {"retryable", true}}}, R"({"type":"error","code":"internal","retryable":true})"},
        {{Type::Ping, {{"t", 123}}}, R"({"type":"ping","t":123})"},
        {{Type::Pong, {{"t", 123}}}, R"({"type":"pong","t":123})"},
    };
    for (const auto& item : messages) {
        CHECK_EQ(encode(item.message), item.json);
        auto decoded = decode(item.json);
        CHECK(decoded);
        CHECK_EQ(encode(*decoded), item.json);
    }
}

TEST(protocol_rejects_malformed) {
    for (std::string_view json : {"{", "{}", R"({"type":true})", R"({"type":"hello"})",
         R"({"type":"ping","t":"7"})", R"({"type":"error","code":"x","retryable":1})",
         R"({"type":"ping","t":1.5})", R"({"type":"x","v":[]})", R"({"type":"x","v":{}})",
         R"({"type":"x","v":null})", R"({"type":"x","v":"\q"})", R"({"type":"x","v":"\uD800"})",
         R"({"type":"x","v":"\uDC00"})", "{\"type\":\"x\",\"v\":\"\xc0\x80\"}",
         "{\"type\":\"x\",\"v\":\"\xed\xa0\x80\"}", R"({"type":"x","type":"ping","t":1})",
         R"({"type":"state","state":"idle","session":"3"})", R"({"type":"state","state":"idle","session":0})",
         R"({"type":"ping","t":01})", R"({"type":"ping","t":9223372036854775808})"})
        CHECK(!decode(json));
    auto unicode = decode(R"({"type":"x","v":"\u3042\uD83D\uDE00"})");
    CHECK(unicode);
    CHECK_EQ(unicode->string("v"), "あ😀");
    std::string json = R"({"type":"x","v":""})";
    json.insert(json.size() - 2, 4096 - json.size(), 'a');
    CHECK(decode(json));
    json.insert(json.size() - 2, 1, 'b');
    CHECK(!decode(json));
}

TEST(protocol_unknown_type_is_ignorable) {
    auto decoded = decode(R"({"type":"future","field":true})");
    CHECK(decoded);
    CHECK_EQ(decoded->type, Type::Unknown);
}

TEST(protocol_escapes_strings) {
    const std::string value = "\"\\\b\f\n\r\t\x01日本語";
    const auto json = encode({Type::Hello, {{"v", 1}, {"token", value}, {"fw", "0.1.0"}}});
    CHECK(json.find(R"(\"\\\b\f\n\r\t\u0001日本語)") != std::string::npos);
    const auto decoded = decode(json);
    CHECK(decoded);
    CHECK_EQ(decoded->string("token"), value);
}

TEST(audio_frame_size_exact_640) {
    CHECK(!validAudioFrame(639));
    CHECK(validAudioFrame(640));
    CHECK(!validAudioFrame(641));
}

TEST(protocol_wake_and_optional_fields) {
    const auto hello = decode(R"({"type":"hello_ok","v":1,"wake":true})");
    CHECK(hello);
    CHECK_EQ(hello->boolean("wake"), true);
    CHECK(!decode(R"({"type":"hello_ok","v":1})")->boolean("wake"));
    const auto tts = decode(R"({"type":"tts_start","sample_rate":16000,"emotion":"sad"})");
    CHECK(tts);
    CHECK_EQ(tts->string("emotion"), "sad");
    CHECK_EQ(decode(R"({"type":"tts_start","sample_rate":16000})")->string("emotion"), "");
    const auto wake = decode(R"({"type":"wake","seq":3,"hit":true})");
    CHECK(wake);
    CHECK_EQ(wake->type, Type::Wake);
    CHECK_EQ(wake->integer("seq"), 3);
    CHECK_EQ(wake->boolean("hit"), true);

    for (std::string_view json : {
         R"({"type":"hello_ok","v":1,"wake":"yes"})", R"({"type":"hello_ok","v":1,"wake":1})",
         R"({"type":"tts_start","sample_rate":16000,"emotion":1})",
         R"({"type":"tts_start","sample_rate":16000,"emotion":true})",
         R"({"type":"tts_start","sample_rate":8000,"emotion":"happy"})",
         R"({"type":"wake_start"})", R"({"type":"wake_start","seq":0})", R"({"type":"wake_start","seq":-1})",
         R"({"type":"wake_start","seq":"1"})", R"({"type":"wake_stop"})", R"({"type":"wake_stop","seq":0})",
         R"({"type":"wake"})", R"({"type":"wake","seq":1})", R"({"type":"wake","hit":true})",
         R"({"type":"wake","seq":0,"hit":true})", R"({"type":"wake","seq":1,"hit":"true"})",
         R"({"type":"wake","seq":1,"hit":1})"})
        CHECK(!decode(json));
    CHECK(encode({Type::WakeStart, {}}).empty());
    CHECK(encode({Type::WakeStop, {{"seq", 0}}}).empty());
    CHECK(encode({Type::Wake, {{"seq", 1}}}).empty());
    CHECK(encode({Type::HelloOk, {{"v", 1}, {"wake", "x"}}}).empty());
    CHECK(encode({Type::TtsStart, {{"sample_rate", 16000}, {"emotion", true}}}).empty());
}
