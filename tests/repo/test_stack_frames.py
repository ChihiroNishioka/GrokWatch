import hashlib
import re
import subprocess
import sys


DISASSEMBLY = """\
40001000 <gwapp::netTask(void*)>:
  1000: 0000 entry a1, 64
  1004: 0000 call8 0x40001010 <gwapp::Network::run()>
  1008: 0000 callx8 a8
  100c: 0000 call8 0x40002000 <m5::M5Unified::begin()>
40001010 <gwapp::Network::run()>:
  1010: 0000 entry a1, 80
  1014: 0000 call4 0x40001020 <grokwatch::decode()>
40001020 <grokwatch::decode()>:
  1020: 0000 entry a1, 160
  1024: 0000 call12 0x40001030 <grokwatch::Parser::object()>
40001030 <grokwatch::Parser::object()>:
  1030: 0000 entry a1, 144
  1034: 0000 call0 0x40001040 <grokwatch::Parser::value()>
40001040 <grokwatch::Parser::value()>:
  1040: 0000 entry a1, 176
  1044: 0000 call8 0x40001050 <grokwatch::Parser::escape()>
40001050 <grokwatch::Parser::escape()>:
  1050: 0000 entry a1, 64
40001060 <gwapp::buttonTask(void*)>:
  1060: 0000 entry a1, 96
40001070 <gwapp::renderTask(void*)>:
  1070: 0000 entry a1, 560
40001080 <gwapp::audioTask(void*)>:
  1080: 0000 entry a1, 64
40001090 <gwapp::touchTask(void*)>:
  1090: 0000 entry a1, 128
400010a0 <grokwatch::unusedLarge()>:
  10a0: 0000 entry a1, 512
40002000 <m5::M5Unified::begin()>:
  2000: 0000 entry a1, 640
"""

APP_MAIN = '''
xTaskCreate(buttonTask, "buttons", 3072, &app, 5, nullptr);
xTaskCreate(renderTask, "render", 6144, &app, 4, nullptr);
xTaskCreate(touchTask, "touch", 4096, &app, 5, nullptr);
xTaskCreate(audioTask, "audio", 6144, &app, 6, nullptr);
xTaskCreate(netTask, "net", 12288, &app, 5, nullptr);
'''


def run_check(tmp_path, repo_root, app_source=APP_MAIN, disassembly=DISASSEMBLY):
    dump = tmp_path / "firmware.dis"
    elf = tmp_path / "firmware.elf"
    app = tmp_path / "app_main.cpp"
    dump.write_text(disassembly)
    elf.write_bytes(b"stack checker test elf\n")
    app.write_text(app_source)
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/check_stack_frames.py"),
            str(elf),
            "--disassembly-file",
            str(dump),
            "--app-main",
            str(app),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    ), hashlib.sha256(elf.read_bytes()).hexdigest()[:9]


def test_stack_checker_uses_direct_call_graph_and_reports_worst_path(tmp_path, repo_root):
    result, digest = run_check(tmp_path, repo_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith(f"ELF SHA256 prefix: {digest}\n")
    assert "gwapp::netTask(void*)[64 B] -> gwapp::Network::run()[80 B] -> " \
        "grokwatch::decode()[160 B] -> grokwatch::Parser::object()[144 B] -> " \
        "grokwatch::Parser::value()[176 B] -> grokwatch::Parser::escape()[64 B]" \
        in result.stdout
    assert "688 + 3,072 = 3,760 / 12,288 B" in result.stdout
    assert "net 外部直接呼び出しの最大実測枠: 640 B  m5::M5Unified::begin()" in result.stdout
    assert "gwapp::unusedLarge()" not in result.stdout
    assert "スタック検査: 合格" in result.stdout


def test_stack_checker_rejects_recursion(tmp_path, repo_root):
    recursive = DISASSEMBLY.replace(
        "40001050 <grokwatch::Parser::escape()>:",
        "40001050 <grokwatch::Parser::escape()>:\n"
        "  1054: 0000 call0 0x40001020 <grokwatch::decode()>",
    )
    result, _ = run_check(tmp_path, repo_root, disassembly=recursive)
    assert result.returncode != 0
    assert "再帰呼び出し" in result.stderr


def test_stack_checker_rejects_unreadable_internal_frame(tmp_path, repo_root):
    unreadable = DISASSEMBLY + "40001100 <grokwatch::noFrame()>:\n  1100: retw\n"
    result, _ = run_check(tmp_path, repo_root, disassembly=unreadable)
    assert result.returncode != 0
    assert "gwapp:: / grokwatch:: 関数の枠を読み取れません" in result.stderr
    assert "grokwatch::noFrame()" in result.stderr


def test_stack_checker_rejects_task_reserve_over_budget(tmp_path, repo_root):
    app_source = APP_MAIN.replace('"net", 12288', '"net", 3700')
    result, _ = run_check(tmp_path, repo_root, app_source=app_source)
    assert result.returncode != 0
    assert "net" in result.stderr
    assert "3,760 B > タスク枠 3,700 B" in result.stderr


def test_stack_checker_rejects_function_over_limit(tmp_path, repo_root):
    disassembly = DISASSEMBLY + "40001100 <grokwatch::oversized()>:\n  1100: entry a1, 2049\n"
    result, _ = run_check(tmp_path, repo_root, disassembly=disassembly)
    assert result.returncode != 0
    assert "grokwatch::oversized(): 2,049 B > 2,048 B" in result.stderr


def test_stack_checker_binds_task_size_to_expected_function(tmp_path, repo_root):
    app_source = APP_MAIN.replace('buttonTask, "buttons"', 'renderTask, "buttons"')
    result, _ = run_check(tmp_path, repo_root, app_source=app_source)
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


def test_audio_pcm_buffers_use_static_storage(repo_root):
    source = (repo_root / "firmware/main/audio_task.cpp").read_text()
    body = source[source.index("void audioTask(void* context)"):]
    assert "static Capture capture;" in body
    assert "static Playback playback;" in body


def test_periodic_stack_diagnostic_covers_every_task(repo_root):
    app = (repo_root / "firmware/main/app_main.cpp").read_text()
    net = (repo_root / "firmware/main/net_task.cpp").read_text()
    assert "&app.netTaskHandle" in app
    assert "&app.audioTaskHandle" in app
    assert "&app.renderTaskHandle" in app
    assert "&app.buttonTaskHandle" in app
    assert "&app.touchTaskHandle" in app
    assert "diag stack free net=%u audio=%u render=%u buttons=%u touch=%u" in net
    assert "auto nextStackReport = nowMs();" in net
    assert "if (now >= nextStackReport)" in net
    assert net.count("uxTaskGetStackHighWaterMark(app_.") == 5
    assert "diag stack net free=%u" not in net
