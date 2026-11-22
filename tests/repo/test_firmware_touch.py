import re


def test_touch_task_continues_without_touch_device(repo_root):
    source = (repo_root / "firmware/main/touch_task.cpp").read_text()
    guard = re.search(r"if\s*\(!touch\)\s*\{(?P<body>.*?)\n\s*\}", source, re.DOTALL)
    assert source.count("M5.Display.touch()") == 1
    assert guard
    assert 'ESP_LOGW("grokwatch", "touch_unavailable")' in guard["body"]
    assert "return;" in guard["body"]
    assert source.index("touch->config()") > guard.end()
    assert source.index("for (;;)") > guard.end()

    render = (repo_root / "firmware/main/render_task.cpp").read_text()
    assert "app.face.frame(app.state, now, level)" in render
