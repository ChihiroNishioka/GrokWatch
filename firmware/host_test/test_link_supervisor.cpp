#include "gw_test.hpp"
#include "grokwatch/link_supervisor.hpp"
#include "grokwatch/avatar_state.hpp"
using namespace grokwatch;

TEST(wifi_drop_and_recover_to_idle) {
    LinkSupervisor link;
    AvatarStateMachine avatar;
    link.wifi(true, 0);
    CHECK_EQ(link.tick(0, .5), LinkAction::Connect);
    CHECK_EQ(link.opened(10), LinkAction::Hello);
    CHECK_EQ(link.authenticated(20), LinkAction::Ready);
    avatar.hello(20);
    CHECK_EQ(avatar.state(), State::Idle);
    CHECK_EQ(link.wifi(false, 30), LinkAction::Disconnect);
    avatar.linkDown(30);
    CHECK_EQ(avatar.state(), State::Disconnected);
    CHECK_EQ(link.tick(1000, .5), LinkAction::None);
    link.wifi(true, 2000);
    CHECK_EQ(link.tick(2000, .5), LinkAction::Connect);
    CHECK_EQ(link.opened(2010), LinkAction::Hello);
    CHECK_EQ(link.authenticated(2020), LinkAction::Ready);
    avatar.hello(2020);
    CHECK_EQ(avatar.state(), State::Idle);
}

TEST(gateway_down_retries_on_backoff_schedule) {
    LinkSupervisor link;
    link.wifi(true, 0);
    CHECK_EQ(link.tick(0, .5), LinkAction::Connect);
    link.failed(0, .5);
    CHECK_EQ(link.tick(999, .5), LinkAction::None);
    CHECK_EQ(link.tick(1000, .5), LinkAction::Connect);
    link.failed(1000, .5);
    CHECK_EQ(link.tick(2999, .5), LinkAction::None);
    CHECK_EQ(link.tick(3000, .5), LinkAction::Connect);
    link.opened(3010);
    link.authenticated(3020);
    link.failed(3030, .5);
    CHECK_EQ(link.tick(4029, .5), LinkAction::None);
    CHECK_EQ(link.tick(4030, .5), LinkAction::Connect);
}

TEST(ping_interval_and_timeout) {
    LinkSupervisor link;
    link.wifi(true, 0);
    link.tick(0, .5);
    link.opened(0);
    link.authenticated(0);
    CHECK_EQ(link.tick(9999, .5), LinkAction::None);
    CHECK_EQ(link.tick(10000, .5), LinkAction::Ping);
    CHECK_EQ(link.tick(20000, .5), LinkAction::Ping);
    CHECK_EQ(link.tick(24900, .5), LinkAction::None);
    CHECK_EQ(link.tick(25000, .5), LinkAction::Disconnect);
}

TEST(auth_error_retries_every_30s) {
    LinkSupervisor link;
    link.wifi(true, 0);
    link.tick(0, .5);
    link.opened(0);
    CHECK_EQ(link.reject(10), LinkAction::Disconnect);
    CHECK(!link.ready());
    CHECK_EQ(link.tick(30009, .5), LinkAction::None);
    CHECK_EQ(link.tick(30010, .5), LinkAction::Connect);
    link.failed(30020, .5);
    CHECK_EQ(link.tick(60019, .5), LinkAction::None);
    CHECK_EQ(link.tick(60020, .5), LinkAction::Connect);
}
