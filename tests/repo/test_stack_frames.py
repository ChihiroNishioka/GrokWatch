import re
import subprocess
import sys


DISASSEMBLY = """\
40000000 <gwapp::netTask(void*)>:
  0: 00c136 entry a1, 64
40000008 <gwapp::readConfig()>:
  8: 00c136 entry a1, 48
4000000c <gwapp::(anonymous namespace)::Network::Network(gwapp::App&, grokwatch::Config)>:
  c: 00c136 entry a1, 32
4000000e <gwapp::(anonymous namespace)::Socket::Socket()>:
  e: 00c136 entry a1, 32
40000010 <gwapp::(anonymous namespace)::Network::run()>:
  10: 00c136 entry a1, 80
40000020 <gwapp::(anonymous namespace)::startWifi()>:
  20: 00c136 entry a1, 368
40000030 <gwapp::(anonymous namespace)::diagScan()>:
  30: 00c136 entry a1, 32
40000040 <gwapp::(anonymous namespace)::Network::pollSocket()>:
  40: 00c136 entry a1, 64
40000050 <gwapp::(anonymous namespace)::Network::receiveText()>:
  50: 00c136 entry a1, 48
40000054 <gwapp::(anonymous namespace)::Network::linkAction()>:
  54: 00c136 entry a1, 288
40000056 <gwapp::(anonymous namespace)::Network::send()>:
  56: 00c136 entry a1, 32
40000057 <gwapp::(anonymous namespace)::Socket::sendText()>:
  57: 00c136 entry a1, 64
40000055 <grokwatch::encode[abi:cxx11](grokwatch::Message const&)>:
  55: 00c136 entry a1, 208
40000058 <grokwatch::decode(std::basic_string_view<char, std::char_traits<char> >)>:
  58: 00c136 entry a1, 160
40000059 <grokwatch::decode(std::basic_string_view<char, std::char_traits<char> >)::{lambda()#1}::operator()() const>:
  59: 00c136 entry a1, 32
4000005c <grokwatch::(anonymous namespace)::Parser::object()>:
  5c: 00c136 entry a1, 144
4000005e <grokwatch::(anonymous namespace)::Parser::value()>:
  5e: 00c136 entry a1, 176
4000005f <grokwatch::(anonymous namespace)::Parser::quoted()>:
  5f: 00c136 entry a1, 64
4000005a <grokwatch::(anonymous namespace)::Parser::escape()>:
  5a: 00c136 entry a1, 64
4000005b <grokwatch::(anonymous namespace)::Parser::hexQuad()>:
  5b: 00c136 entry a1, 80
4000005d <grokwatch::(anonymous namespace)::hasFields()>:
  5d: 00c136 entry a1, 336
4000005b <grokwatch::Message::string()>:
  5b: 00c136 entry a1, 80
40000060 <gwapp::(anonymous namespace)::Network::capture()>:
  60: 00c136 entry a1, 32
40000070 <gwapp::(anonymous namespace)::Network::pollWifi()>:
  70: 00c136 entry a1, 48
40000080 <gwapp::buttonTask(void*)>:
  80: 00c136 entry a1, 96
40000090 <grokwatch::VolumeKeys::sample()>:
  90: 00c136 entry a1, 48
400000a0 <gwapp::renderTask(void*)>:
  a0: 00c136 entry a1, 560
400000b0 <gwapp::renderTask(void*)::{lambda()#1}::operator()() const>:
  b0: 00c136 entry a1, 224
400000c0 <gwapp::FaceAnimator::frame()>:
  c0: 00c136 entry a1, 176
400000d0 <gwapp::drawFace()>:
  d0: 00c136 entry a1, 256
400000e0 <grokwatch::scaleFace()>:
  e0: 00c136 entry a1, 64
400000f0 <gwapp::drawRing()>:
  f0: 00c136 entry a1, 32
40000100 <gwapp::audioTask(void*)>:
  100: 00c136 entry a1, 2688
40000110 <gwapp::Capture::pump()>:
  110: 00c136 entry a1, 32
40000120 <gwapp::captureFault()>:
  120: 00c136 entry a1, 32
40000130 <gwapp::Playback::pump()>:
  130: 00c136 entry a1, 112
40000135 <gwapp::Playback::stop()>:
  135: 00c136 entry a1, 32
40000140 <gwapp::Playback::fault()>:
  140: 00c136 entry a1, 32
40000150 <gwapp::Playback::dmaTail()>:
  150: 00c136 entry a1, 32
"""

APP_MAIN = '''
xTaskCreate(buttonTask, "buttons", 3072, &app, 5, nullptr);
xTaskCreate(renderTask, "render", 6144, &app, 4, nullptr);
xTaskCreate(audioTask, "audio", 6144, &app, 6, nullptr);
xTaskCreate(netTask, "net", 12288, &app, 5, nullptr);
'''


def run_check(tmp_path, repo_root, app_source=APP_MAIN, disassembly=DISASSEMBLY):
    dump = tmp_path / "firmware.dis"
    app = tmp_path / "app_main.cpp"
    dump.write_text(disassembly)
    app.write_text(app_source)
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/check_stack_frames.py"),
            "--disassembly-file",
            str(dump),
            "--app-main",
            str(app),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


def test_stack_frame_checker_accepts_paths_within_budget(tmp_path, repo_root):
    result = run_check(tmp_path, repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "net Wi-Fi 診断走査" in result.stdout
    assert "スタック検査: 合格" in result.stdout


def test_stack_frame_checker_rejects_function_over_limit(tmp_path, repo_root):
    disassembly = DISASSEMBLY + "40000200 <grokwatch::oversized()>:\n  200: entry a1, 2049\n"
    result = run_check(tmp_path, repo_root, disassembly=disassembly)
    assert result.returncode != 0
    assert "grokwatch::oversized(): 2,049 B > 2,048 B" in result.stderr


def test_stack_frame_checker_rejects_task_path_over_budget(tmp_path, repo_root):
    app_source = APP_MAIN.replace('"net", 12288', '"net", 3500')
    result = run_check(tmp_path, repo_root, app_source=app_source)
    assert result.returncode != 0
    assert "net Wi-Fi 診断走査" in result.stderr
    assert "3,616 B > タスク枠 3,500 B" in result.stderr


def test_stack_frame_checker_binds_task_size_to_expected_function(tmp_path, repo_root):
    app_source = APP_MAIN.replace('buttonTask, "buttons"', 'renderTask, "buttons"')
    result = run_check(tmp_path, repo_root, app_source=app_source)
    assert result.returncode != 0
    assert "app_main.cpp の buttons タスクは buttonTask を起動してください" in result.stderr


def test_net_task_does_not_allocate_network_on_its_stack(repo_root):
    source = (repo_root / "firmware/main/net_task.cpp").read_text()
    body = source[source.index("void netTask(void* context)"):]
    assert not re.search(r"(?m)^\s*(?!static\b)Network\s+\w+", body)


def test_diag_scan_keeps_ap_records_out_of_its_stack(repo_root):
    source = (repo_root / "firmware/main/net_task.cpp").read_text()
    body = source[source.index("void diagScan("):source.index("bool startWifi(")]
    assert "static std::array<wifi_ap_record_t, 20> aps{};" in body
    assert not re.search(
        r"(?m)^\s*(?!static\b)(?:std::array<wifi_ap_record_t,\s*20>\s+\w+|"
        r"wifi_ap_record_t\s+\w+\s*\[\s*20\s*\])",
        body,
    )
    start_wifi = source[source.index("bool startWifi("):source.index("class Socket")]
    assert "(diagScan(config), true)" in start_wifi
    assert source.count("diagScan(") == 2
    run_start = source.index("void run()")
    run_end = source.index("\nprivate:", run_start)
    assert "startWifi(config_, wifiEvents_)" in source[run_start:run_end]
    assert source.count("startWifi(") == 2
