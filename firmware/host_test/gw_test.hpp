#pragma once
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Test {
    using Run = void (*)();
    static inline Test* first = nullptr;
    const char* name;
    Run run;
    Test* next;
    Test(const char* name, Run run) : name(name), run(run), next(first) { first = this; }
};

#define TEST(name) static void name(); static Test register_##name(#name, name); static void name()
#define CHECK(expr) do { if (!(expr)) { \
    std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); std::exit(1); \
} } while (false)
#define CHECK_EQ(a, b) CHECK((a) == (b))
#define CHECK_NEAR(a, b, tolerance) CHECK(std::abs((a) - (b)) <= (tolerance))

int main(int argc, char** argv) {
    bool ran = false;
    for (auto test = Test::first; test; test = test->next) {
        if (argc == 1 || std::strcmp(test->name, argv[1]) == 0) {
            test->run();
            ran = true;
        }
    }
    return ran ? 0 : 1;
}
