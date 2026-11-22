#include "gw_test.hpp"
#include "grokwatch/face_model.hpp"
#include <vector>
using namespace grokwatch;

TEST(idle_and_disconnected_drift) {
    for (auto state : {State::Idle, State::Disconnected})
        for (unsigned seed : {1, 17, 99}) {
            FaceAnimator face(seed, 0);
            SeededRandom rng(seed);
            Drift drift;
            std::vector<Vec> points;
            Millis lastTarget = 0;
            for (Millis time = 0; time <= 30000; time += 10) {
                points.push_back(face.frame(state, time).gaze);
                const auto sample = drift.update(time, rng);
                CHECK(std::hypot(sample.target.x, sample.target.y) <= 0.35 + 1e-6);
                if (sample.newTarget && time != 0) {
                    CHECK(time - lastTarget >= 1500 && time - lastTarget <= 4000);
                    lastTarget = time;
                }
            }
            CHECK(lastTarget >= 26000);
            for (size_t first = 0; first + 500 < points.size(); ++first) {
                bool moved = false;
                for (size_t i = first + 1; i <= first + 500 && !moved; ++i)
                    moved = std::hypot(points[i].x - points[first].x,
                                       points[i].y - points[first].y) >= .02;
                CHECK(moved);
            }
        }
}
