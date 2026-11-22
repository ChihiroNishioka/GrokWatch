import re


def test_volume_buttons_use_gpio_and_start_task(repo_root):
    firmware = repo_root / "firmware/main"
    task = (firmware / "button_task.cpp").read_text()
    app = (firmware / "app_main.cpp").read_text()
    assert "gpio_get_level(static_cast<gpio_num_t>(grokwatch::volumeButtonUpGpio))" in task
    assert "gpio_get_level(static_cast<gpio_num_t>(grokwatch::volumeButtonDownGpio))" in task
    for forbidden in ("M5.update(", "M5.Speaker", "M5.Mic", "app.gestures", "BtnPWR", "M5.Power"):
        assert forbidden not in task
    assert 'xTaskCreate(buttonTask, "buttons"' in app
    for path in firmware.glob("*.cpp"):
        source = path.read_text()
        for forbidden in ("M5.update(", "BtnA", "BtnB", "BtnPWR", "M5.Power"):
            assert forbidden not in source, f"{path}: {forbidden}"


def test_volume_is_applied_by_audio_task_only(repo_root):
    firmware = repo_root / "firmware/main"
    audio = (firmware / "audio_task.cpp").read_text()
    board = (firmware / "board.cpp").read_text()
    assert "M5.Speaker.setVolume(" in audio
    assert "defaultVolumeValue" in audio
    assert "app.volume.value()" in audio
    assert "volume != appliedVolume" in audio
    assert "M5.Speaker" not in board and "M5.Mic" not in board
    assert "M5.Speaker.config(" in audio
    assert "M5.Mic.isEnabled()" in audio and "M5.Speaker.isEnabled()" in audio
    assert "configureAudio()" in board
    assert audio.index("bool configureAudio()") < audio.index("void audioTask(")
    assert audio.index("M5.Speaker.config(config)") < audio.index("M5.Speaker.setVolume(appliedVolume)")
    assert "config.magnification = grokwatch::speakerMagnification" in audio
    assert board.index("configureAudio()") < board.index("M5.Display.setRotation")
    assert (firmware / "app_main.cpp").read_text().index("if (!initBoard())") < (
        firmware / "app_main.cpp"
    ).read_text().index("xTaskCreate(")
    for path in firmware.glob("*.cpp"):
        if path.name != "audio_task.cpp":
            source = path.read_text()
            assert "M5.Speaker" not in source, path
            assert "M5.Mic" not in source, path


def test_render_scales_face_from_locked_volume(repo_root):
    source = (repo_root / "firmware/main/render_task.cpp").read_text()
    lock = source.index("const Lock lock(app.mutex)")
    volume = source.index("app.volume.value()", lock)
    face = source.index("app.face.frame(app.state, now, level)", lock)
    assert volume < source.index("}();", lock)
    assert face < source.index("}();", lock)
    assert "scaleFace(" in source and "avatarScale(" in source
    assert "drawFace(sprite, frame.first, grokwatch::avatarScale(frame.second))" in source
    assert "fillCircle(faceCenter, faceCenter, faceRadius," not in source
    assert "volume bar" not in source.lower()


def test_button_changes_do_not_enter_gesture_path(repo_root):
    source = (repo_root / "firmware/main/button_task.cpp").read_text()
    assert "app.gestures" not in source
    assert "GestureEvent" not in source
    assert "M5.update(" not in source
    assert "ESP_LOGI(\"grokwatch\", \"volume value=%u\"" in source


def test_speaker_begin_failure_is_cleaned_up_without_unrunning_end(repo_root):
    build = (repo_root / "firmware/CMakeLists.txt").read_text()
    source = (repo_root / "firmware/main/audio_task.cpp").read_text()
    assert "Speaker_Class.cpp" in build
    assert "_cb_set_enabled(_cb_set_enabled_args, false)" in build
    assert "_i2s_driver_uninstall(_cfg.i2s_port)" in build
    assert re.search(r"if\s*\(M5\.Speaker\.isRunning\(\)\)\s*M5\.Speaker\.end\(\)", source)
    assert source.count("M5.Speaker.end()") == 1
    assert source.index("stop();", source.index("M5.Speaker.playRaw(")) < source.index(
        "fault(app);", source.index("M5.Speaker.playRaw(")
    )


def test_audio_stops_speaker_before_capture_and_keeps_playback_exclusive(repo_root):
    source = (repo_root / "firmware/main/audio_task.cpp").read_text()
    loop = source[source.index("for (;;) {", source.index("void audioTask")):]
    assert loop.index("playback.stop();") < loop.index("capture.pump(")
    assert loop.index("capture.pump(") < loop.index("playback.pump(")


def test_diagnostic_logs_drop_ssid_lengths_keep_categories(repo_root):
    source = (repo_root / "firmware/main/net_task.cpp").read_text()
    assert "target_bytes" not in source
    assert "non-ascii ap bytes=%u" not in source
    assert '"diag scan:' in source
    assert '"diag wifi:' in source
    assert '"diag ws:' in source
    for call in re.findall(r"\bESP_LOG[A-Z_]+\s*\((.*?);", source, re.DOTALL):
        assert not re.search(
            r"\b(?:ssid|password|token|host|port|ip_info|target_bytes)\b|bytes=", call, re.IGNORECASE
        )
